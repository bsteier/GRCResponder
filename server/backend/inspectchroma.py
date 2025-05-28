import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

client = chromadb.PersistentClient(path="./test_db")
collections = client.list_collections()

print("Collections found:")
for col in collections:
    print(col)

# Check one specific collection (adjust name if needed)
name = "test_collection"  # or replace with one listed above
collection = client.get_or_create_collection(
    name=name,
    embedding_function=SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
)

print(f"\n{name} contains {collection.count()} documents.")
