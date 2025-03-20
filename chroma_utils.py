import chromadb
from sentence_transformers import SentenceTransformer
import pdfplumber
from io import BytesIO
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from chromadb import Collection
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

'''
Function that will add a document w/ given metadata to the referenced Chroma collection
'''
def addToChroma(docs_metadata: list, collection: Collection, embedding_args: dict):
    try:
        session = createSession()
    except Exception as e:
        print(f'Failed to create session: {e}')
        return
    
    for doc in docs_metadata:
        doc_link = doc['source_url']

        try:
            pdf_response = session.get(doc_link,stream=True, timeout=5)
            pdf_response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f'Failed to access PDF {doc_link} with exception: {e}')
            continue

        pdf_file = BytesIO(pdf_response.content)
        pdf = pdfplumber.open(pdf_file)
        pdf_text = '\n'.join([page.extract_text() for page in pdf.pages if page.extract_text()])

        uploadToChroma(collection, embedding_args, pdf_text, doc)


def createSession():
    try:
        session = requests.Session()
        # set headers for session
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)Chrome/58.0.3029.110 Safari/537.3'})
        # allow for retries
        retry_strategy = Retry(
        total=3,
        status_forcelist=[500, 502, 503, 504],
        backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session
    except Exception as e:
        print(f'Failed to start session:{e}')
        raise e


def uploadToChroma(collection: Collection, embedding_args: str, pdf_text: str, doc):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=embedding_args['chunk_size'], chunk_overlap=embedding_args['chunk_overlap'])
    chunks = text_splitter.split_text(pdf_text)

    # get embeddings
    metadatas = [
        {
            'chunk_index': i,
            'document_id': doc['document_id'],
            'proceeding_id': doc['proceeding_id'],
            'source_url': doc['source_url'],
            'text': chunk
        }
        for i, chunk in enumerate(chunks)
    ]
    
    ids = [f'{doc["document_id"]}_{i}' for i in range(len(chunks))]
    
    collection.add(
        ids=ids,
        metadatas=metadatas,
        documents=chunks
    )
    
    print(f'Uploaded {doc["document_id"]} to ChromaDB')
    return