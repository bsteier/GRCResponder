# I am making this file to allow for LLM code to be worked on separately
# use wrapper functions to help with testing and such

from pathlib import Path
from langgraph.graph import MessagesState, StateGraph
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.prebuilt import ToolNode
from langgraph.graph import END
from langchain_core.documents import Document
import time
import io
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
import json
from typing import List, Dict, Any
import uuid
from qdrant_client import QdrantClient, models
import os
from dotenv import load_dotenv
from retrieval import retrieve, set_collection
from langchain_google_genai import ChatGoogleGenerativeAI
import asyncio
import time
from tenacity import AsyncRetrying, stop_after_attempt, RetryError, wait_exponential, retry
from qdrant_client.http.models import Filter, FieldCondition, MatchAny
import re
from advanced_retrieval import crossEncoderQuery

# load in environment variables
env_path = "../../.env"
load_dotenv(dotenv_path=env_path)
QDRANT_CONNECT = os.getenv("QDRANT_CONNECT")
COLLECTION_NAME ='GRC_Documents_Large'
GOOGLE_API = os.getenv("GOOGLE_API_KEY")

try:
    qdrant_client = QdrantClient(url=QDRANT_CONNECT)
    collections = qdrant_client.get_collections()

    print("Collections:r")
    for collection in collections.collections:
        print(f"- {collection.name}")
except Exception as e:
    print(f"Error connecting to Qdrant: {e}")

set_collection(qdrant_client)

# Provided retrieve tool for querying DB, Search Engine Team will write code replacing
# this to allow for query expansion
def set_api_key(api_key_variable: Path):
    os.environ["GOOGLE_API_KEY"] = api_key_variable

def initialize_llm(gemini_model = 'gemini-2.0-flash'):
    set_api_key(GOOGLE_API)
    llm = ChatGoogleGenerativeAI(model=gemini_model, max_tokens=None)
    return llm

llm = initialize_llm()

# Graphs nodes =====================================
class ChatHistoryManager:
    def __init__(self, max_history_length=10):
        self.sessions = {}
        self.max_history_length = max_history_length

    def get_or_create_session(self, session_id: str) -> List:
        """Get or create a new chat session"""
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        return self.sessions[session_id]

    def add_message(self, session_id: str, message) -> None:
        """Add a message to the chat history"""
        history = self.get_or_create_session(session_id)
        history.append(message)

        if len(history) > self.max_history_length * 2:  # Keep pairs of messages
            self.sessions[session_id] = history[-self.max_history_length*2:]

    def get_history(self, session_id: str) -> List:
        """Get the chat history for a session"""
        return self.get_or_create_session(session_id)

    def clear_history(self, session_id: str) -> None:
        """Clear the chat history for a session"""
        self.sessions[session_id] = []

    def save_history(self): # TODO: STORE HISTORY TO FILE
        pass

    def load_history(self): # TODO: LOAD HISTORY FROM FILE
        pass

chat_manager = ChatHistoryManager(max_history_length=15)



### CODE TO CLASSIFY THE MESSAGES ###############################
def pre_filter_query(query: str):
    """
    Pre-filter queries to determine processing branch.
    You can easily modify this to add new classifications.
    """
    classification_prompt = f"""Classify this query into ONE category:

1. GRC_SPECIFIC - Any question about:
    - California utilities (PG&E, SCE, SDG&E, etc.)
    - Rate cases, revenue requirements, testimony, exhibits
    - CPUC proceedings, decisions, or regulations
    - Anything a regulatory analyst might need to know
    - Questions referencing previous conversation or context
    - ANY question where retrieved documents MIGHT be helpful

2. GRC_GENERAL - ONLY the most basic definitional questions like:
    - "What does GRC stand for?"
    - "What is a General Rate Case?"
    - "What does CPUC mean?"
    (Use ONLY when you're 100% certain no documents would help)

3. NON_GRC - ONLY for clearly off-topic requests like:
    - Recipes, games, jokes, personal advice
    - Non-utility topics (movies, sports, health)
    - Obvious chatbot misuse

4. GRC_LONGFORM - It is absolutely clear this response needs an essay. A paragraph or two clearly wont do.

IMPORTANT: When in doubt, choose GRC_SPECIFIC. We want to help users with any utility-related questions.

Query: {query}

Respond with ONLY the category name (GRC_SPECIFIC, GRC_GENERAL, NON_GRC, or GRC_LONGFORM)."""

    try:
        # Create a simple message for classification
        classification_messages = [
            SystemMessage(content="You are a classifier for California GRC regulatory queries. Respond with only the category name."),
            HumanMessage(content=classification_prompt)
        ]

        response = llm.invoke(classification_messages)
        category = response.content.strip().upper()

        # Ensure the category exists in our configuration
        if category not in QUERY_BRANCHES:
            category = "GRC_SPECIFIC"  # Default fallback

        print(f"Pre-filter classification: {category}")
        return category

    except Exception as e:
        # If classification fails, default to GRC_SPECIFIC
        print(f"Pre-filter error: {e}")
        return "GRC_SPECIFIC"


def create_branch_retrieval_node(branch_name: str):
    """Create a retrieval node for a specific branch."""
    def branch_retrieval(state: QueryMessagesState):
        branch_config = QUERY_BRANCHES[branch_name]
        if not branch_config["has_retrieval"]:
            # Skip retrieval for this branch
            return {"messages": state["messages"]}

        # Get the latest human message
        latest_human_message = None
        for message in reversed(state["messages"]):
            if message.type == "human":
                latest_human_message = message
                break

        if latest_human_message is None:
            return {"messages": state["messages"]}

        # Create a tool call for retrieval with branch specific k value
        tool_call_id = str(uuid.uuid4())
        retrieval_message = AIMessage(
            content=f"I'll search for relevant information to answer your {branch_name.lower().replace('_', ' ')} question.",
            tool_calls=[{
                "name": "retrieve",
                "id": tool_call_id,
                "args": {"query": latest_human_message.content, "k": branch_config["retrieval_k"]}
            }]
        )

        return {
            "messages": state["messages"] + [retrieval_message]
        }

    return branch_retrieval


def create_branch_generate_node(branch_name: str):
    """Create a generate node for a specific branch."""
    def branch_generate(state: QueryMessagesState):
        branch_config = QUERY_BRANCHES[branch_name]

        # Get filter message
        if branch_config["filter_message"]:
            response_message = AIMessage(content=branch_config["filter_message"])
            return {"messages": [response_message]}

        # Get system prompt for branch
        system_prompt = branch_config["system_prompt"]

        # If this branch has retrieval, get the retrieved documents
        if branch_config["has_retrieval"]:
            # Get generated ToolMessages
            recent_tool_messages = []
            for message in reversed(state["messages"]):
                if message.type == "tool":
                    recent_tool_messages.append(message)
                else:
                    break
            tool_messages = recent_tool_messages[::-1]

            # Format document context if available
            docs_content = "\n\n".join(doc.content for doc in tool_messages)
            system_prompt = system_prompt.format(document_context=f"Document Context: {docs_content}")
        else:
            # No document context for non-retrieval branches
            system_prompt = system_prompt.format(document_context="")

        # Get conversation messages excluding tool messages and tool-calling AI messages
        conversation_messages = []
        
        for message in state["messages"]:
            if message.type == "human":
                conversation_messages.append(message)
            elif message.type == "ai" and not getattr(message, "tool_calls", None):
                conversation_messages.append(message)

        prompt = [SystemMessage(content=system_prompt)] + conversation_messages

        print(f"Generating response for branch: {branch_name}")
        print(f"Prompt for {branch_name} branch: {prompt}")

        # Run llm
        response = llm.invoke(prompt)
        return {"messages": [response]}

    return branch_generate

QUERY_BRANCHES = {
    "NON_GRC": {
        "has_retrieval": False,
        "retrieval_k": 0,
        "filter_message": ("I'm specifically designed to assist with California General Rate Case (GRC) proceedings and CPUC regulatory matters. "
        "How can I help you with GRC-related questions, rate case analysis, or utility regulatory issues?"),
        "system_prompt": """You are a GRC specialist. Politely redirect non-GRC queries back to GRC topics."""
    },
    "GRC_GENERAL": {
        "has_retrieval": False,
        "retrieval_k": 0,
        "filter_message": None,
        "system_prompt": """<SYSTEM>
You are "GRC Regulatory Analysis Expert," an AI assistant specialized in California GRC proceedings.
</SYSTEM>
<IDENTITY AND EXPERTISE>
You are a regulatory specialist focused exclusively on California General Rate Case (GRC) proceedings and related CPUC filings.
</IDENTITY AND EXPERTISE>
<RESPONSE FORMAT>
Provide clear, concise definitions and explanations for basic GRC concepts. Use markdown formatting for readability.
</RESPONSE FORMAT>
<SCOPE LIMITATIONS>
Address only topics related to California GRC proceedings and CPUC regulatory matters.
</SCOPE LIMITATIONS>
Always end responses with: "Would you like me to explore any aspect of this response in greater depth or address related regulatory considerations?"
"""
    },
    "GRC_SPECIFIC": {
        "has_retrieval": True,
        "retrieval_k": 8,
        "filter_message": None,
        "system_prompt": """<SYSTEM>
You are "GRC Regulatory Analysis Expert," an AI assistant specialized in California GRC proceedings.
</SYSTEM>

<INFORMATION SOURCES>
Base your responses EXCLUSIVELY on:
1. Retrieved documents (HIGHEST PRIORITY)
2. User-provided context in the current session

The retrieval system has already provided you with the most relevant information.
Always cite your sources with specific references (e.g., "PG&E 2023 GRC, Exhibit 4, p.15").
Always link to the original document, it should be provided as part of the context.
</INFORMATION SOURCES>

<IDENTITY AND EXPERTISE>
You are a regulatory specialist focused exclusively on California General Rate Case (GRC) proceedings and related CPUC filings with expertise in:
- Rate case applications and testimony
- Revenue requirement analysis
- Procedural requirements and timelines
- CPUC decisions and precedents
</IDENTITY AND EXPERTISE>

<RESPONSE FORMAT>
Structure your responses with:
1. Concise summary of key findings
2. Detailed analysis with multiple supporting citations
3. Relevant regulatory background and historical context
4. Discussion of practical implications
5. Complete citations formatted as markdown links

Use markdown formatting (headers, tables, bullets) to enhance readability.
</RESPONSE FORMAT>

<PROFESSIONAL TONE>
Maintain a voice that is:
- Authoritative yet accessible
- Technically precise
- Thorough and explanatory
- Objective in regulatory interpretation
</PROFESSIONAL TONE>

<ACCURACY REQUIREMENTS>
- Never invent citations, docket numbers, or proceedings
- Clearly indicate when information is missing or insufficient
- Present multiple interpretations when guidance is ambiguous
- Quote directly from sources for critical regulatory language
</ACCURACY REQUIREMENTS>

<SCOPE LIMITATIONS>
Address only topics related to California GRC proceedings and CPUC regulatory matters.
For other topics, politely explain they fall outside your expertise.
</SCOPE LIMITATIONS>

Always end responses with: "Would you like me to explore any aspect of this response in greater depth or address related regulatory considerations?"

{document_context}
""" # document_context gets replaced by actual documents in retrieval
    },
    "GRC_LONGFORM": {
        "has_retrieval": False,
        "retrieval_k": 10,
        "filter_message": None,
        "system_prompt": None
    }
}

# Class that allows for query_classification to be stored in state
class QueryMessagesState(MessagesState):
    query_classification: str = "GRC_SPECIFIC"


# =============  LONGFORM RETRIEVAL AND EXECUTION ==============================

schema = {
    "type": "object",
    "properties": {
        "subquery":{
            "type": "string",
            "description": "A specific subquery derived from the user query for efficient document retrieval.",
            "examples": "Describe key aspects of Pacific Gas and Electric's (PG&E) 2023 General Rate Case application."
        },
        "search_strings":{
            "type": "array",
            "items": {
                "type": "string",
                "description": "A search string derived from the subquery that will be used to retrieve relevant documents from the vector database. We include multiple in case the subquery involves multiple aspects or entities.",
            },
            "description": "A list of search strings that will be used to retrieve relevant documents from the vector database.",
            "maxItems": 2,
            "minItems": 1
        },
        "proceeding_id":{
            "type": "array",
            "items":{
                "type": "string",
                "description": "The unique identifier for the proceeding related to the subquery extracted from the subquery if available.",
                "examples": ["A.23-03-005", "A.21-06-021"]
            },
            "description": "List of unique identifiers for the proceeding related to the subquery. This field should only be populated if the id of the proceeding is clearly stated in the original user query.",
        }
    }
}

SUBQUERY_PROMPT = f"""
You are a tool in a retrieval-augmented generation (RAG) system. Your job is to decompose a complex user query into specific and focused subqueries, each paired with relevant search strings. These subqueries will be used to retrieve relevant documents from a vector database.

Important:

- DO NOT answer the user query.

- You are NOT allowed to summarize, explain, or discuss the topic.

- Only return a list of JSON objects in the schema format below.

- Each subquery must be a JSON object with the following fields:

- Only add to the proceeding_id metadata field if the id of the proceeding is CLEARLY STATED in the original user query.

- If there is potential for multiple proceedings, do not include the proceeding_id field in the JSON object.

Schema:
{schema}

Only return a list of such JSON objects, without any extra commentary, explanation, or markdown formatting.

"""


def retrieve_context(query: str, k: int = 8, search_filter: Filter = None) -> str:
    """Retrieve information related to a query."""
    # Query qdrant directly
    if not qdrant_client:
        raise ValueError("Qdrant client is not initialized. Please set the QDRANT_CONNECT environment variable.")
    results = None

    results = crossEncoderQuery(
        qdrant_client=qdrant_client,
        query=query,
        collection_name=COLLECTION_NAME,
        k=k,
        search_filter = search_filter 
    )
    if not results:
        results = crossEncoderQuery(
            qdrant_client=qdrant_client,
            query=query,
            collection_name=COLLECTION_NAME,
            k=k,
            search_filter=None  # Fallback without filter
        )
    # Format results for LangChain compatibility
    retrieved_docs = []
    for result in results:
        doc_id = result.payload['document_id']
        content = result.payload['text']
        metadata = {k: v for k, v in result.payload.items() if k != 'text'} if result.payload else {}

        doc = Document(page_content=content, metadata=metadata)
        retrieved_docs.append(doc)

    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\n" f"Content: {doc.page_content} Document Link: {doc.metadata.get('source_url', 'N/A')}")
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs

def getFormattedQuery(subquery: Dict[str, Any]):
    search_strings = subquery.get("search_strings", [])
    proceeding_ids = subquery.get("proceeding_id", []) # list of potential IDs to search through
    subquery_text = subquery.get("subquery", "")

    for i,proceeding in enumerate(proceeding_ids):
        # we need to format it so it can be used in the query, remove everything but the alphanumeric characters
        proceeding_ids[i] = re.sub(r'[^A-Za-z0-9]', '', proceeding)# Remove non-alphanumeric characters
        print(f"Proceeding ID {i}: {proceeding_ids[i]}")
        
    if not len(proceeding_ids):
        proceeding_ids = None # if no proceeding ids, set to None so its like no filter
    
    # create filter for proceeding_id if it exists
    query_filter = None
    if proceeding_ids:
        query_filter = Filter(
            must=[
                models.FieldCondition(
                    key="proceeding_id",
                    match=models.MatchAny(any=proceeding_ids)
                )
            ]
        )

    search_result = retrieve_context(
        query=search_strings[0], # use first string for retrieval, will modify later to use all and combine
        k=8,
        search_filter = query_filter
    )

    formatted_query = f"""
    You are "GRC Regulatory Analysis Expert," an AI assistant specialized in California GRC proceedings.
                </SYSTEM>

                <INFORMATION SOURCES>
                Base your responses EXCLUSIVELY on:
                1. Retrieved documents (HIGHEST PRIORITY)
                2. User-provided context in the current session

                The retrieval system has already provided you with the most relevant information.
                Always cite your sources with specific references (e.g., "PG&E 2023 GRC, Exhibit 4, p.15").
                </INFORMATION SOURCES>

                <IDENTITY AND EXPERTISE>
                You are a regulatory specialist focused exclusively on California General Rate Case (GRC) proceedings and related CPUC filings with expertise in:
                - Rate case applications and testimony
                - Revenue requirement analysis
                - Procedural requirements and timelines
                - CPUC decisions and precedents
                </IDENTITY AND EXPERTISE>

                <RESPONSE FORMAT>
                Structure your responses with:
                1. Concise summary of key findings
                2. Detailed analysis with multiple supporting citations
                3. Relevant regulatory background and historical context
                4. Discussion of practical implications
                5. Throughout your response, for example after each bullet point, supply a list of markdown links to the sources you used to generate that part of the response as a comma seperated list.
                

                Use markdown formatting (headers, tables, bullets) to enhance readability.
                </RESPONSE FORMAT>

                <PROFESSIONAL TONE>
                Maintain a voice that is:
                - Authoritative yet accessible
                - Technically precise
                - Thorough and explanatory
                - Objective in regulatory interpretation
                </PROFESSIONAL TONE>

                <ACCURACY REQUIREMENTS>
                - Never invent citations, docket numbers, or proceedings
                - Clearly indicate when information is missing or insufficient
                - Present multiple interpretations when guidance is ambiguous
                - Quote directly from sources for critical regulatory language
                </ACCURACY REQUIREMENTS>

                <SCOPE LIMITATIONS>
                Address only topics related to California GRC proceedings and CPUC regulatory matters.
                For other topics, politely explain they fall outside your expertise.
                </SCOPE LIMITATIONS>

                Always end responses with: "Would you like me to explore any aspect of this response in greater depth or address related regulatory considerations?"

                Document Context: {search_result[0]}

                User Query: {subquery_text}
                """

    return formatted_query

async def process_subqueries(original_query:str, subqueries: str):
    """
    Process the subqueries to ensure they are in the correct format.
    """
    # Manually cleaning the response since gemini does not seem to be able to
    cleaned_response = subqueries.strip()
    if cleaned_response.startswith("```json"):
        cleaned_response = cleaned_response.lstrip("```json").strip()
    if cleaned_response.endswith("```"):
        cleaned_response = cleaned_response.rstrip("```").strip()
    print(cleaned_response)
    
    try:
        response_json = json.loads(cleaned_response)
    except json.JSONDecodeError:
        print("Failed to parse response as JSON. Here's the raw content:")
        return None
    
    combined_responses = ''
    queries = []

    for i,item in enumerate(response_json):
        queries.append(
            {
            'query': item['subquery'],
            'index': i,
            'prompt': getFormattedQuery(item)
            }
        )
    print(queries)
    combined_queries =  await multiThreadedQueries(queries)
    formatted_return = '\n\n'.join(combined_queries)
    answer = await combineSubqueries(original_query, formatted_return)

    return answer

async def combineSubqueries(original_query:str, formatted_answers: str):
    combine_queries_prompt = f"""
    You are an expert in regulatory analysis, tasked with combining multiple subqueries into a single, coherent response.
    
    Please synthesize the responses to all previous subqueries into a comprehensive analysis of the California GRC proceedings, ensuring all relevant details are integrated and presented coherently. Focus on providing a unified understanding of the regulatory landscape and its implications.

    Ensure that the final response is well-structured, and maintains the same level of detail and professionalism as the individual subquery responses. Do your best to keep the responses and thorough as possible, maintaining enough details from each subquery answer.

    To make the response more seamless, act as though this is a single response to the original user query, and not a response to multiple subqueries.

    Maintain formatting such as bullets, headers, and markdown links from the original subqueries. Do not say "The provided documents" in the response, instead refer to context as "availible data".

    ORIGINAL USER QUERY:
    {original_query}
    
    SUBQUERIES AND RESPONSES:
    
    """

    final_prompt = combine_queries_prompt + formatted_answers
    messages = [HumanMessage(content=final_prompt)]
    result = llm.invoke(messages)
    return result if isinstance(result, AIMessage) else AIMessage(content="Failed to synthesize subqueries.")
    


@retry(
    wait=wait_exponential(multiplier=1, min=4, max=10),
    stop=stop_after_attempt(3)
)
async def asyncQueryLLM(query: Dict[str, Any]) -> str:
    prompt = query.get('prompt', "")

    if not prompt:
        raise ValueError("Prompt is empty or not provided in the query dictionary.")

    try:
        messages = [HumanMessage(content=prompt)]
        response = await llm.ainvoke(messages)
        llm_response = response.content if isinstance(response, AIMessage) else "Failed to retrieve response for Subquery\n"
        
        formatted_response = f"""
        Subquery {query['index'] + 1}:\n{query["query"]}\nGenerated Response:\n{llm_response}\n
        """
        return formatted_response

    except Exception as e:
        print(f"Error querying LLM: {e}")
        raise e

async def multiThreadedQueries(queries: List[str]):
    tasks = []
    for query in queries:
        tasks.append(asyncQueryLLM(query))
    
    results = []

    for future in asyncio.as_completed(tasks):
        try:
            result = await future
            results.append(result)
        except RetryError as e:
            print(f"RetryError in async task: {e}")
            results.append("Error processing subquery after retries.")
        except Exception as e:
            print(f"Error in async task: {e}")
            results.append("Error processing subquery.")

    # sort by query index
    results.sort(key=lambda x: int(re.search(r'Subquery (\d+):', x).group(1)) - 1)
    return results


# ========================================================================



async def execute_longform(state: QueryMessagesState) -> Dict[str, Any]:
    """
    Run longform generation
    """
    print("Executing self-contained GRC_LONGFORM branch...")

    # Get config
    branch_config = QUERY_BRANCHES["GRC_LONGFORM"]
    latest_human_message = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)

    if not latest_human_message:
        # Fallback if no human message is found
        return {"messages": [AIMessage(content="I'm sorry, I couldn't find your query.")]}

    query = latest_human_message.content
    retrieval_k = branch_config["retrieval_k"]

    # EXECUTE LONGFORM
    combined_prompt = SUBQUERY_PROMPT + f"\nUser Query: {query}\n"
    # Get subquery generated by LLM
    response = await llm.ainvoke([HumanMessage(content=combined_prompt)])

    answer = await process_subqueries(query, response.content)
    if not answer:
        answer = AIMessage(content="I'm sorry, I couldn't generate a response for your query.")
    return {"messages": [answer]}
#####################################################################
# Build the graph
def build_graph():
    graph_builder = StateGraph(QueryMessagesState)

    # Node to classify the user's query
    def classifier_node(state: QueryMessagesState):
        """Classify the query and add classification to state metadata."""
        latest_human_message = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)

        if not latest_human_message:
            return {"messages": state["messages"], "query_classification": "GRC_SPECIFIC"}

        category = pre_filter_query(latest_human_message.content)
        return {"messages": state["messages"], "query_classification": category}

    def route_to_branch(state: QueryMessagesState):
        print(f"State passed to route_to_branch: {state}")
        classification = state.get("query_classification", "GRC_SPECIFIC")
        if classification == "GRC_LONGFORM":
            # Just run longform response
            return "execute_longform"
        else:
            # Go to standard retrieval nodes for other branches
            return f"retrieve_{classification.lower()}"

    # Set up the graph connections
    graph_builder.add_node("classifier", classifier_node)
    graph_builder.add_node("tools", ToolNode([retrieve]))
    graph_builder.add_node("execute_longform", execute_longform)

    # Dynamically create and connect nodes for all standard branches
    for branch_name, config in QUERY_BRANCHES.items():
        if branch_name == "GRC_LONGFORM": # Skip the custom branch in this loop
            continue

        retrieval_node_name = f"retrieve_{branch_name.lower()}"
        graph_builder.add_node(retrieval_node_name, create_branch_retrieval_node(branch_name))

        generate_node_name = f"generate_{branch_name.lower()}"
        graph_builder.add_node(generate_node_name, create_branch_generate_node(branch_name))

        # Connect edges for standard branches
        if config["has_retrieval"]:
            # Path for branches that use the ToolNode
            graph_builder.add_edge(retrieval_node_name, "tools")
            graph_builder.add_edge("tools", generate_node_name)
        else:
            # Path for branches that do not use tools
            graph_builder.add_edge(retrieval_node_name, generate_node_name)

        graph_builder.add_edge(generate_node_name, END)

    graph_builder.set_entry_point("classifier")
    graph_builder.add_conditional_edges(
        "classifier",
        route_to_branch,
    )

    graph_builder.add_edge("execute_longform", END)

    return graph_builder.compile()

# Initialize the graph
graph = build_graph()


def process_query(query: str, session_id: str, retrieval_k: int = 8, enable_prefilter: bool = True) -> Dict[str, Any]:
    """
    Process a query with dynamic branch routing.

    Args:
        query: The user's query
        session_id: Session identifier for chat history
        retrieval_k: Number of documents to retrieve (can be overridden by branch config)
        enable_prefilter: Whether to apply pre-filtering (default: True)
    """
    start_time = time.time()

    # Get chat history
    history = chat_manager.get_history(session_id)

    # Format messages
    messages = []
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "tool":
            # Create a tool message with appropriate attributes and a tool_call_id
            messages.append(ToolMessage(
                content=msg["content"],
                name=msg.get("tool_name", "retrieve"),
                tool_call_id=msg.get("tool_call_id", str(uuid.uuid4()))
            ))

    # Add the current query
    messages.append(HumanMessage(content=query))

    # Run the graph
    result = None
    tool_outputs = []
    query_classification = None

    # Process the query through the graph
    with io.StringIO() as buf, redirect_stdout(buf):
        for step in graph.stream(
            {"messages": messages},
            stream_mode="values",
        ):
            # Get classification if available
            if "query_classification" in step:
                query_classification = step["query_classification"]

            last_message = step["messages"][-1]
            if last_message.type == "tool":
                tool_outputs.append({
                    "tool_name": getattr(last_message, "name", "retrieve"),
                    "content": last_message.content
                })
            if last_message.type == "ai" and not getattr(last_message, "tool_calls", None):
                result = last_message.content

        debug_output = buf.getvalue()

    end_time = time.time()
    elapsed_time = end_time - start_time

    # Add messages to chat history (excluding classification messages)
    chat_manager.add_message(session_id, {"role": "user", "content": query})

    # Add tool messages to history
    for tool_output in tool_outputs:
        chat_manager.add_message(session_id, {
            "role": "tool",
            "content": tool_output["content"],
            "tool_name": tool_output.get("tool_name", "retrieve")
        })

    if result:
        chat_manager.add_message(session_id, {"role": "assistant", "content": result})

    response = {
        "result": result,
        "processing_time": elapsed_time,
        "tool_outputs": tool_outputs,
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "debug_output": debug_output if debug_output else None,
        "query_classification": query_classification,
        "branch_used": query_classification,
        "filtered_out": query_classification == "NON_GRC"
    }

    return response

def get_available_branches():
    """Get list of all available query branches."""
    return list(QUERY_BRANCHES.keys())

def get_chat_history(session_id: str):
    return chat_manager.get_history(session_id)

def clear_chat_history(session_id: str):
    chat_manager.clear_history(session_id)
    return {"status": "success", "message": f"Chat history cleared for session {session_id}"}

def generate_session_id():
    return str(uuid.uuid4())

class LLMChatSession():
    def __init__(self, console_mode = False) -> None:
        self.session_id = generate_session_id()
        self.console_mode = console_mode
        self.timestamp_queue = [] # New ones get inserted at end (using append); remove by deleting element 0
        self.max_queries = 15
        # When query, update message queue; if still at limit then stop, otherwise
    def query(self, user_input: str, k = None) -> Dict[str, Any]:
        # if self.is_under_limit():
        if k is None:
            response = process_query(user_input, self.session_id)
        else:
            response = process_query(user_input, self.session_id, k)

        if self.console_mode:
            print(f"\nGRC Assistant: {response['result']}")
            print(f"\nProcessing time: {response['processing_time']:.2f} seconds")
        self.timestamp_queue.append(datetime.fromisoformat(response['timestamp']))
        return {'result': response['result'],
                'messages_remaining': self.max_queries - sum([(datetime.now() - timestamp).seconds < 60 for timestamp in self.timestamp_queue]),
                'sec_remaining': [60 - (datetime.now() - timestamp).seconds for timestamp in self.timestamp_queue],
                'tool_outputs': response['tool_outputs'],
                }
        # else:
        #     raise ConnectionRefusedError(f"Rate Limit Exceeded | Try again in {60 - (datetime.now() - self.timestamp_queue[0]).seconds} seconds")


    def is_under_limit(self) -> bool:
        while len(self.timestamp_queue) > 0:
            if (datetime.now() - self.timestamp_queue[0]).seconds > 60: # Is over 60 sec time limit
                del self.timestamp_queue[0]
                continue
            else:
                break
        return len(self.timestamp_queue) < 15

    def hist_free_query(self, user_input: str) -> Dict[str, Any]:
        clear_chat_history(self.session_id)
        out = self.query(user_input)
        clear_chat_history(self.session_id)
        return out

async def getAIResponse(message: str):

    start_time = time.time()

    # Go through the graph
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": message}]}
    )

    # Extract response
    ai_messages = [msg for msg in result["messages"] if msg.type == "ai" and not msg.tool_calls]

    end_time = time.time()
    elapsed_time = end_time - start_time

    if ai_messages:
        response = {
            "role": "ai",
            "content": ai_messages[-1].content,
            "elapsed_time": f"{elapsed_time:.2f} seconds"
        }
    else:
        response = {
            "role": "ai",
            "content": "Could not generate response.",
            "elapsed_time": f"{elapsed_time:.2f} seconds",
        }
    
    return response

if __name__ == "__main__":
    # use this to test the api call and ensure everything is initialized
    test_message = 'What is the revenue requirement for PG&E in the 2023 GRC?'
    print(getAIResponse("Tell me about the 2023 GRC for PG&E"))
