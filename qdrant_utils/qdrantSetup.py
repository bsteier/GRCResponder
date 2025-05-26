from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
import os
from dotenv import load_dotenv

load_dotenv()
QDRANT_CONNECT= os.getenv('QDRANT_CONNECT')
COLLECTION_NAME = os.getenv('EMBEDDING_COLLECTION')

def create_Qdrant_collection(qdrant_client, name, embedding_size):
    try:
        qdrant_client.create_collection(
            collection_name = name,
            vectors_config=VectorParams(
                size=embedding_size,
                distance=Distance.COSINE
            )
        )
        print(f"Successfully created collection: {name}")
    except Exception as e:
        print(f"Failed to create collection {name}: {e}")
        return None

if __name__ == "__main__":
    # Create database w/ embedding function, size of all-Mini embeddings are 384
    client = QdrantClient(url=QDRANT_CONNECT)
    create_Qdrant_collection(client, COLLECTION_NAME, 384)
    