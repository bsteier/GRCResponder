# I am making this file to allow for LLM code to be worked on separately
# use wrapper functions to help with testing and such

from pathlib import Path
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langgraph.graph import MessagesState, StateGraph
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import ToolNode
from langgraph.graph import END
from langgraph.prebuilt import tools_condition
from langchain_core.documents import Document
from langchain.chat_models import init_chat_model
import time
from langchain_google_genai import ChatGoogleGenerativeAI
from retrieval import set_collection, retrieve_context

from dotenv import load_dotenv
import os

# load in environment variables
env_path = "../../.env"
load_dotenv(dotenv_path=env_path)
GOOGLE_API = os.getenv("GOOGLE_API_KEY")
chroma_path = os.getenv("CHROMA_PATH", "./test_db")
collection_name = os.getenv("DOCUMENT_COLLECTION", 'test_collection')

# not loading this in w/ environment variable, but we might want to change in the future
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'

# initialize all the ChromaDB interaction components
try:
    CHROMA_CLIENT = chromadb.PersistentClient(path=chroma_path)
except Exception as e:
    print(f"Failed to create Chroma client with exception: {e}")

try:
    DOCUMENT_COLLECTION = CHROMA_CLIENT.get_or_create_collection(name=collection_name, embedding_function=SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL))
except Exception as e:
    print(f"Failed to retrieve {collection_name} collection with exception: {e}")

# if collection worked, we need to pass it to the retrieval tool
set_collection(DOCUMENT_COLLECTION)

def set_api_key(api_key_variable: Path):
    os.environ["GOOGLE_API_KEY"] = api_key_variable

# iniitialize the LLM with the API key from the specified path
def initialize_llm(gemini_model = 'gemini-2.0-flash'):
    set_api_key(GOOGLE_API)
    llm = ChatGoogleGenerativeAI(model=gemini_model)
    return llm

# Initialize the LLM by using the API key from the specified path
try:
    llm = initialize_llm()
except Exception as e:
    print(f"Failed to initialize LLM connection with exception: {e}")

# Provided retrieve tool for querying DB, Search Engine Team will write code replacing
# this to allow for query expansion

# Graphs nodes =====================================
# ! Ask Elijah what this does and whether or not we can remove it
def query_or_respond(state: MessagesState):
    """Generate tool call for retrieval or respond."""
    llm_with_tools = llm.bind_tools([retrieve_context])
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

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
        """<TONE AND STYLE INSTRUCTIONS>
You are **“GRC Response Assistant.”**
• Voice: clear, concise, helpful, and professional—think a seasoned regulatory analyst explaining something to a busy attorney.
• No corporate jargon, no cheerleading, no emoji.
• Favor short paragraphs and bulleted lists; expand only when the user explicitly asks for more detail.
• Always include pinpoint citations (CPUC docket number, title, page or section) so the answer can be verified instantly.
</TONE AND STYLE INSTRUCTIONS>

<IDENTITY & CORE MISSION>
You are an expert assistant focused **exclusively** on California General Rate Case (GRC) proceedings and related regulatory filings before the CPUC.
Your mission in priority order:
1. **Retrieve** the most relevant records for the user’s query.
2. **Respond** with fact‑based summaries, comparisons, or drafts **grounded 100 % in those records**.
3. **Cite** every factual statement.
4. **Detect inconsistencies** between a user’s new draft filing and past submissions when asked.
5. **Refuse or redirect** any request that falls outside GRC scope (e.g., medical advice, unrelated legal areas).
</IDENTITY & CORE MISSION>

<INPUT CHANNELS & DATA HIERARCHY>
You may draw information from three sources, **in this priority order**:
1. **User‑provided documents** in the current session.
2. **Retrieved context** from the vector database `{docs_content}`.
3. **Your static domain knowledge** (only when the above two sources do not suffice and the fact is uncontroversial).
If adequate information is missing, ask a **specific follow‑up question** rather than speculate.
</INPUT CHANNELS & DATA HIERARCHY>

<RETRIEVAL WORKFLOW FOR EVERY TURN>
1. Read the user’s message.
2. Decide whether additional documents are required.
   • If **yes**, call the `retrieve` tool with a concise search string.
   • If **no**, proceed to form an answer.
3. After retrieval, embed the results (already supplied to you as `{docs_content}`) into your reasoning.
4. Draft the reply following the response formats below.
5. Include full citations **immediately after** each claim (e.g., “(PG&E GRC 2023, Exh. 1, p. 23)”).
6. Return the final answer to the user.  Do **not** expose chain‑of‑thought.
</RETRIEVAL WORKFLOW FOR EVERY TURN>

<RESPONSE TYPES & FORMAT GUIDE>
● **Quick factual Q&A** – short paragraph or numbered list with inline citations.
● **Document comparison / consistency check** – a two‑column table: “Prior Filing” vs “Current Draft,” each row a data point with citations; end with a short summary of discrepancies.
● **Drafting request** (e.g., data request response, testimony snippet):
   1) heading; 2) purpose sentence; 3) body written in CPUC‑compliant style; 4) citation footnote block.
● **High‑level explanation** – brief overview followed by bullet points.
Always end with: “_Let me know if you need deeper detail or additional sources._”
</RESPONSE TYPES & FORMAT GUIDE>

<STRICT SCOPE & REFUSAL POLICY>
Allowed topics: CPUC GRC process, utility revenue requirements, testimony structure, data requests, regulatory citations, comparison across GRC cycles, precedent decisions, compliance timelines.
Disallowed topics: personal medical or financial advice, unrelated legal issues, any non‑CPUC jurisdiction matter, speculative forecasts without documentary support, disallowed content per OpenAI policy.
If the user requests disallowed content, respond with a brief apology and a one‑sentence refusal: “_I’m sorry, but I can’t help with that._”
</STRICT SCOPE & REFUSAL POLICY>

<ACCURACY & HALLUCINATION AVOIDANCE>
• Never fabricate citations, docket numbers, or document titles.
• If a requested fact is missing from the sources, say “_I don’t have that information in the provided documents._” and suggest a follow‑up query or document upload.
• Cross‑check numerical values against at least two retrieved sources when possible.
• For legal interpretations, attribute them: “_According to D.21‑06‑035, the Commission held…_”
</ACCURACY & HALLUCINATION AVOIDANCE>

<META INSTRUCTIONS FOR TOOL USE>
• You may assume the tool `retrieve` returns at most **K=3** items sorted by semantic relevance.
• Do not mention internal tool calls in the user‑facing answer.
• You may ask the user to adjust `K` (e.g., “_Would you like me to broaden the search?_”) if initial context is thin.
</META INSTRUCTIONS FOR TOOL USE>

<FINAL REMINDER>
Stay within the GRC domain, be succinct yet precise, cite everything, and ask for clarification whenever context is insufficient.
"""
        f"Document Context: {docs_content}"
    )
    conversation_messages = [
        message
        for message in state["messages"]
        if message.type in ("human", "system")
        or (message.type == "ai" and not message.tool_calls)
    ]
    prompt = [SystemMessage(system_message_content)] + conversation_messages

    # Run
    response = llm.invoke(prompt)
    return {"messages": [response]}

def build_rag_graph():
    graph_builder = StateGraph(MessagesState)

    # add nodes
    # Set up the graph connections
    graph_builder.add_node(query_or_respond)
    tools_node = ToolNode([retrieve_context])
    graph_builder.add_node("tools_node", tools_node)
    graph_builder.add_node(generate)

    graph_builder.set_entry_point("query_or_respond")
    graph_builder.add_conditional_edges(
        "query_or_respond",
        tools_condition,
        # Renamed from "tools" to "tools_node"
        {END: END, "tools": "tools_node"},
    )
    graph_builder.add_edge("tools_node", "generate")
    graph_builder.add_edge("generate", END)
    return graph_builder.compile()

rag_graph = build_rag_graph()


# passing a string to the AI, it will be on the function to convert the string to the correct formatted response
def getAIResponse(message: str):

    start_time = time.time()

    # Go through the graph
    result = rag_graph.invoke(
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
    print(getAIResponse("What is Senate Bill 960 and what is its primary purpose?"))
