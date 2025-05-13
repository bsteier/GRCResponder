from langchain_core.documents import Document
from langchain_core.tools import tool

K = 3
DOCUMENT_COLLECTION = None  # Placeholder for the ChromaDB collection

def set_collection(collection):
    """Set the ChromaDB collection for retrieval."""
    global DOCUMENT_COLLECTION
    DOCUMENT_COLLECTION = collection

@tool(response_format="content_and_artifact")
def retrieve_context(query: str):
    """Retrieve information related to a query."""
    global K

    # Query ChromaDB directly
    results = DOCUMENT_COLLECTION.query(
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


    return serialized, retrieved_docs