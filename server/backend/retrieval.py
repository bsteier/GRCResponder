from langchain_core.documents import Document
from langchain_core.tools import tool
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from advanced_retrieval import query_db, crossEncoderQuery, hydeRetrieval, hydeCrossEncoderRetrieval

import os
from dotenv import load_dotenv
load_dotenv(dotenv_path="../../.env")

K = 8
print(f"DOCUMENT_COLLECTION: {os.getenv('DOCUMENT_COLLECTION')}")

DOCUMENT_COLLECTION = "GRC_Documents_Large"
qdrant_client = None
embedding_model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
embedding_function = SentenceTransformer(embedding_model_name)

def set_collection(client: QdrantClient):
    """Set the ChromaDB collection for retrieval."""
    global qdrant_client
    qdrant_client = client

@tool(response_format="content_and_artifact")
def retrieve(query: str, k: int = 8):
    """Retrieve information related to a query."""
    # Query qdrant directly

    print("retrieve")
    try: 
        results = crossEncoderQuery(
            query=query,
            qdrant_client=qdrant_client,
            collection_name=DOCUMENT_COLLECTION,
            k=k
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
            (f"Source: {doc.metadata}\n" f"Content: {doc.page_content}")
            for doc in retrieved_docs
        )
    except Exception as e:
        print (e)
    return serialized, retrieved_docs