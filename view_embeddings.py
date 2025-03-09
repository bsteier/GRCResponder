import os
import chromadb
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
CHROMA_HOST = os.getenv("CHROMA_HOST")


def cDB_client():
    if CHROMA_HOST:
        parsed_url = urlparse(CHROMA_HOST)
        host = parsed_url.hostname
        port = parsed_url.port or 8000

        print(f"connecting to chromaDB : {CHROMA_HOST}")
        return chromadb.HttpClient(host=host, port=port)
    else:
        print("local ChromaDB")
        return chromadb.Client()


def list_collections(client):
    print("\n--- collections in ChromaDB ---")
    collections = client.list_collections()
    print(f"Found {len(collections)} collection(s):")
    for collection_name in collections:
        print(f"  - {collection_name}")
    return collections


def view_collection_data(client, collection_name="invalid-collection-name"):
    print(f"\n--- Viewing data for collection: '{collection_name}' ---")
    collection = client.get_collection(name=collection_name)

    results = collection.get(include=["embeddings", "metadatas", "documents"])
    item_count = len(results['ids'])

    print(f"Collection '{collection_name}' contains {item_count} item(s).")

    # metadata for each item
    for i, (item_id, metadata) in enumerate(zip(results['ids'], results['metadatas'])):
        print(f"\nItem {i + 1}:")
        print(f"  ID: {item_id}")
        print(f"  Document ID: {metadata.get('document_id')}")
        print(f"  Proceeding ID: {metadata.get('proceeding_id')}")
        print(f"  Chunk Index: {metadata.get('chunk_index')}")
        print(f"  Source URL: {metadata.get('source_url')}")

        # Show a preview of the text (first 100 characters)
        text = metadata.get('text', '')
        if len(text) > 100:
            text_preview = text[:100] + "..."
        else:
            text_preview = text
        print(f"  Text Preview: {text_preview}")

        if 'embeddings' in results and results['embeddings'] is not None and i < len(results['embeddings']):
            embedding = results['embeddings'][i]
            print(f"  Embedding dimensions: {len(embedding)}")
        else:
            print("  Embedding dimensions: Not available")


def main():
    collection = input("Enter the collection name: ")
    print(f"\nSelected collection: {collection}")
    client = cDB_client()
    list_collections(client)
    view_collection_data(client, collection)


if __name__ == "__main__":
    main()
