# I am making this file to allow for LLM code to be worked on separately
# use wrapper functions to help with testing and such

from pathlib import Path
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
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
from qdrant_client import QdrantClient
import os
from dotenv import load_dotenv
from retrieval import retrieve, set_collection
from langchain_google_genai import ChatGoogleGenerativeAI

# load in environment variables
env_path = "../../.env"
load_dotenv(dotenv_path=env_path)
QDRANT_CONNECT = os.getenv("QDRANT_CONNECT")
COLLECTION_NAME = os.getenv("DOCUMENT_COLLECTION")
GOOGLE_API = os.getenv("GOOGLE_API_KEY")

try:
    qdrant_client = QdrantClient(url=QDRANT_CONNECT)
except Exception as e:
    print(f"Error connecting to Qdrant: {e}")

set_collection(qdrant_client)

# Provided retrieve tool for querying DB, Search Engine Team will write code replacing
# this to allow for query expansion
def set_api_key(api_key_variable: Path):
    os.environ["GOOGLE_API_KEY"] = api_key_variable

def initialize_llm(gemini_model = 'gemini-2.0-flash'):
    set_api_key(GOOGLE_API)
    llm = ChatGoogleGenerativeAI(model=gemini_model)
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

# Set up retrieval tool
# @tool(response_format="content_and_artifact")
# def retrieve(query: str, k: int = 8):
#     """Retrieve information related to a query."""
#     # Query ChromaDB directly
#     # embedding = embedding_function.encode(query).tolist()

#     # response = qdrant_client.query_points(
#     #     collection_name=COLLECTION_NAME,
#     #     query=embedding, # I changed this from list to just one embedding
#     #     limit=k,
#     #     with_payload=True,
#     # )
#     # results = [points for points in response.points]
    
#     results = crossEncoderQuery(
#         query=query,
#         qdrant_client=qdrant_client,
#         collection_name=COLLECTION_NAME,
#         k=k
#     )

#     # Format results for LangChain compatibility
#     retrieved_docs = []
#     for result in results:
#         doc_id = result.payload['document_id']
#         content = result.payload['text']
#         metadata = {k: v for k, v in result.payload.items() if k != 'text'} if result.payload else {}

#         doc = Document(page_content=content, metadata=metadata)
#         retrieved_docs.append(doc)

#     serialized = "\n\n".join(
#         (f"Source: {doc.metadata}\n" f"Content: {doc.page_content}")
#         for doc in retrieved_docs
#     )
#     return serialized, retrieved_docs

# Build the graph
def build_graph():
    graph_builder = StateGraph(MessagesState)

    def force_retrieval(state: MessagesState):
        """Always call the retrieve tool first."""
        # Get the latest human message
        latest_human_message = None
        for message in reversed(state["messages"]):
            if message.type == "human":
                latest_human_message = message
                break

        if latest_human_message is None:
            return {"messages": state["messages"]}

        # Create a tool call for retrieval with a properly formatted tool_calls attribute
        tool_call_id = str(uuid.uuid4())
        retrieval_message = AIMessage(
            content="I'll search for relevant information to answer your question.",
            tool_calls=[{
                "name": "retrieve",
                "id": tool_call_id,
                "args": {"query": latest_human_message.content, "k": 8}
            }]
        )

        return {
            "messages": state["messages"] + [retrieval_message]
        }

    # Execute the retrieval
    tools = ToolNode([retrieve])

    # Generate a response using the retrieved content
    def generate(state: MessagesState):
        """Generate answer."""
        # Get generated ToolMessages
        recent_tool_messages = []
        for message in reversed(state["messages"]):
            if message.type == "tool":
                recent_tool_messages.append(message)
            else:
                break
        tool_messages = recent_tool_messages[::-1]

        # Format into prompt
        docs_content = "\n\n".join(doc.content for doc in tool_messages)
        system_message_content = (
            """<SYSTEM>
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
                """
            f"Document Context: {docs_content}"
        )
        conversation_messages = []
        for message in state["messages"]:
            if message.type == "human":
                conversation_messages.append(message)
            elif message.type == "ai" and not getattr(message, "tool_calls", None):
                conversation_messages.append(message)

        prompt = [SystemMessage(system_message_content)] + conversation_messages

        # Run llm
        response = llm.invoke(prompt)
        return {"messages": [response]}

    # Set up the graph connections
    graph_builder.add_node("force_retrieval", force_retrieval)
    graph_builder.add_node("tools", tools)
    graph_builder.add_node("generate", generate)

    graph_builder.set_entry_point("force_retrieval")
    graph_builder.add_edge("force_retrieval", "tools")
    graph_builder.add_edge("tools", "generate")
    graph_builder.add_edge("generate", END)

    return graph_builder.compile()

# Initialize the graph
graph = build_graph()

def process_query(query: str, session_id: str, retrieval_k: int = 8) -> Dict[str, Any]:
    # Set the K value for this query
    retrieve.bind(k=retrieval_k)

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

    # Process the query through the graph
    with io.StringIO() as buf, redirect_stdout(buf):
        for step in graph.stream(
            {"messages": messages},
            stream_mode="values",
        ):
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

    # Add messages to chat history
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
        "debug_output": debug_output if debug_output else None
    }

    return response

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

def getAIResponse(message: str):

    start_time = time.time()

    # Go through the graph
    result = graph.invoke(
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
