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

chroma_path = "./test_db"
collection_name = 'test_collection'
embedding_model_name = 'all-MiniLM-L6-v2'


client = chromadb.PersistentClient(path=chroma_path)
embedding_function = SentenceTransformerEmbeddingFunction(model_name=embedding_model_name)


collection = client.get_or_create_collection(name=collection_name, embedding_function=embedding_function)


llm = init_chat_model("llama3.2:3b-instruct-q8_0", model_provider="ollama")

# Set up retrieval tool
K = 3  # Default number of documents to retrieve

@tool(response_format="content_and_artifact")
def retrieve(query: str):
    """Retrieve information related to a query."""
    global K
    # Query ChromaDB directly
    results = collection.query(
        query_texts=[query],
        n_results=K,
    )

    # Format results for LangChain compatibility
    retrieved_docs = []
    for i in range(len(results['ids'][0])):
        doc_id = results['ids'][0][i]
        content = results['documents'][0][i]
        metadata = results['metadatas'][0][i] if results['metadatas'][0] else {}


        doc = Document(page_content=content, metadata=metadata)
        retrieved_docs.append(doc)

    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\n" f"Content: {doc.page_content}")
        for doc in retrieved_docs
    )
    # print(retrieved_docs,serialized)
    return serialized, retrieved_docs

# Build the graph
graph_builder = StateGraph(MessagesState)

def query_or_respond(state: MessagesState):
    """Generate tool call for retrieval or respond."""
    llm_with_tools = llm.bind_tools([retrieve])
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

# Step 2: Execute the retrieval
tools = ToolNode([retrieve])

# Step 3: Generate a response using the retrieved content
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
        "You are an assistant for question-answering tasks. "
        "You are an expert on general rate cases. "
        "Use the following pieces of retrieved context to answer "
        "the question. If you don't know the answer, say that you "
        "don't know."
        "\n\n"
        f"{docs_content}"
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

# Set up the graph connections
graph_builder.add_node(query_or_respond)
graph_builder.add_node(tools)
graph_builder.add_node(generate)

graph_builder.set_entry_point("query_or_respond")
graph_builder.add_conditional_edges(
    "query_or_respond",
    tools_condition,
    {END: END, "tools": "tools"},
)
graph_builder.add_edge("tools", "generate")
graph_builder.add_edge("generate", END)

graph = graph_builder.compile()

# Main loop for interaction
def main():
    show_tool_output = True  # Set to True if you want to see tool outputs
    while True:
        input_message = input()
        if input_message == "exit":
            break

        start_time = time.time()

        for step in graph.stream(
            {"messages": [{"role": "user", "content": input_message}]},
            stream_mode="values",
        ):
            if show_tool_output:
                step["messages"][-1].pretty_print()
            else:
                evnt = step["messages"][-1]
                if (type(evnt) == HumanMessage or type(evnt) == AIMessage) and evnt.content != '':
                    evnt.pretty_print()

        end_time = time.time()

        elapsed_time = end_time - start_time
        print(f"\n========================\n\tLLM call took {elapsed_time:.2f} seconds\n========================\n")
