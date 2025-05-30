from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
import fitz
from io import BytesIO
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import os


load_dotenv(dotenv_path="../.env")
QDRANT_CONNECT = os.getenv('QDRANT_CONNECT')
if QDRANT_CONNECT is None:
    raise ValueError("QDRANT_CONNECT environment variable not set.")

EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
COLLECTION_NAME = os.getenv('EMBEDDING_COLLECTION')

model = SentenceTransformer(EMBEDDING_MODEL)
qdrant_client = QdrantClient(url=QDRANT_CONNECT)
default_embedding_args = {
    'chunk_size': 1024,
    'chunk_overlap': 50
}

def create_embeddings_from_pdf(file_bytes: bytes, embedding_args=default_embedding_args, embedding_model=EMBEDDING_MODEL):
    pdf_file = BytesIO(file_bytes)
    pdf = fitz.open(stream=pdf_file, filetype='pdf')
    pdf_text = ''

    for page in pdf:
        pdf_text += page.get_text('text')
        pdf_text += '\n\n'
    
    # use overlap to create chunks
    text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=embedding_args['chunk_size'],
            chunk_overlap=embedding_args['chunk_overlap']
        )

    chunks = text_splitter.split_text(pdf_text)
    embeddings = create_embeddings_from_text(chunks, model)
    return embeddings

# This function will take a string (pdf text) and will return the embeddings,
# id, and text for each chunk of tet
def create_embeddings_from_text(chunks: str, embedding_model) -> list:
    embeddings = []
    for i, chunk in enumerate(chunks):
        embedding = embedding_model.encode(chunk)
        embeddings.append({
            'chunk_index': i,
            'embedding': embedding,
            'text': chunk
        })
    return embeddings


def create_qdrant_points(ids:list, embeddings:list, payloads:list):
    points = []
    for i, embedding in enumerate(embeddings):
        point = PointStruct(
            id=ids[i],
            vector=embeddings[i],
            payload=payloads[i]
        )
        points.append(point)
    return points


def upload_to_qdrant(points:list, collection_name=COLLECTION_NAME):
    try:
        qdrant_client.upsert(
            collection_name=collection_name,
            points=points
        )
        print(f"Successfully uploaded {len(points)} points to Qdrant.")
    except Exception as e:
        print(f"Failed to upload points to Qdrant: {e}")