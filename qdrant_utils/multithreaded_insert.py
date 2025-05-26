import json
import os
import uuid
import threading
from queue import Queue, Empty
from sentence_transformers import SentenceTransformer
import torch
import threading
import fitz
from io import BytesIO
from langchain.text_splitter import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from dotenv import load_dotenv
import os
from qdrant_client.http.models import PointStruct, VectorParams, Distance
import threading
import time #for monitoring

load_dotenv()
QDRANT_CONNECT = os.getenv('QDRANT_CONNECT')
qdrant_client = QdrantClient(url='QDRANT_CONNECT')

LOCAL_PATH = '/workspace/CPUCDocuments/' # Replace to directory with all proceeding folders
BATCH_SIZE = 256
QUEUE_MAXSIZE = 100

# Arguments for embedding
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 50

# When tested, one producer thread seemed to be sufficient, it was more bottlednecked w/ embedding creation and upload
finished_producers_lock = threading.Lock()
FINISHED_PRODUCERS = 0
NUM_PRODUCERS = 1

DOCUMENT_COUNT = 0

# collection stuff
COLLECTION_NAME = os.getenv('EMBEDDING_COLLECTION') # Renamed so dont accidentally delete

# Queue that will be shared between the Embedding thread and the file splitter thread as well as the embedding thread and the upload thread
chunks_queue = Queue(maxsize=QUEUE_MAXSIZE)
embedding_queue = Queue(maxsize=QUEUE_MAXSIZE)
proceedings_queue = Queue()

# Load model, should be GPU if available
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
if device.type == 'cpu':
    print("No GPU available, using CPU for embedding.")
else:
    print("Using GPU!")

model = SentenceTransformer('all-MiniLM-L6-v2', device=device)

# Debugging sanity checks
print(f"Model device: {model.device}")
print(f"Model on GPU: {next(model.parameters()).is_cuda}")
print(f"Available GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
print(f"GPU memory used: {torch.cuda.memory_allocated() / 1e9:.3f} GB")


# Lock for set to check if document has been processed
seen_lock = threading.Lock()
seen = set()

def generateProceedings():
    if not os.path.exists(LOCAL_PATH):
        print(f"Directory {LOCAL_PATH} does not exist.")
        return
    
    proceedings = [proceeding for proceeding in os.listdir(LOCAL_PATH) if os.path.isdir(os.path.join(LOCAL_PATH, proceeding))]
    for proceeding in proceedings:
        proceedings_queue.put(proceeding)
    print(f'Found {len(proceedings)} proceedings to process.')


# ================ Code that will create Embeddings ==================

def embedding_thread():
    # Just to help with keeping track, we will print every 1000 chunks printed
    print_count = 0
    current_points = []

    while True:
        # get the chunks from the queue
        try:
            
            start_time = time.time()
            current_chunks = chunks_queue.get()
            get_time = time.time() - start_time

            if current_chunks is None:
                break
                
            embed_start = time.time()
            curr_batch = [chunk['text'] for chunk in current_chunks]
            embeddings = model.encode(curr_batch)
            
            # After each embedding batch, clear cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()  # Clear unused cached memory
            
            embed_time = time.time() - embed_start
            
            print(f"Queue get time: {get_time:.2f}s, Embedding time: {embed_time:.2f}s for embedding of size {len(curr_batch)}", flush=True)

            ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{chunk['document_id']}_{chunk['chunk_index']}")) for chunk in current_chunks]

            payloads = [
                {
                    'chunk_index': chunk['chunk_index'],
                    'document_id': chunk['document_id'],
                    'proceeding_id': chunk['proceeding_id'],
                    'source_url': chunk['source_url'],
                    'published_date': chunk['published_date'],
                    'year': chunk['year'],
                    'title': chunk['title'],
                    'doc_type': chunk['doc_type'],
                    'text': chunk['text']
                } for chunk in current_chunks
            ]

            # create points for qdrant
            points = create_qdrant_points(ids, embeddings, payloads)
            current_points.extend(points)

            if len(current_points) >= 1000:
                embedding_queue.put(current_points)
                current_points = []
                print(f"chunks_queue length: {chunks_queue.qsize()}", flush=True)

            print_count += len(current_chunks)

            if print_count % 10000 == 0:
                print(f"Processed {print_count} chunks.", flush=True)

        except Exception as e:
            print(f"Error processing chunks in embedding thread: {e}", flush=True)
            continue
    
    # Upload remaining points
    if current_points:
        embedding_queue.put(current_points)
    
    # Upload None to signal end of processing
    embedding_queue.put(None)
    print("Finished processing all chunk embeddings", flush=True)


def create_qdrant_points(ids:list, embeddings:list, payloads:list):
    points = []
    for i, embedding in enumerate(embeddings):
        point = PointStruct(
            id=ids[i],
            vector=embeddings[i].tolist(),
            payload=payloads[i]
        )
        points.append(point)
    return points

# ====================================================================

# ================ Points uploader thread code =======================
def upload_thread():

    total_uploaded = 0

    while True:
        try:
            # get the points from the queue
            current_points = embedding_queue.get()

            if current_points is None:
                print("Received None in upload thread, stopping.", flush=True)
                break
            
            for i in range(3): # try to insert 3 times else continue
                try:
                    qdrant_client.upsert(
                        collection_name=COLLECTION_NAME,
                        points=current_points
                    )
                    break  # If successful, break out of the retry loop
                except Exception as e:
                    print(f"Error uploading points to Qdrant: {e}. Retrying {i+1}/3...", flush=True)
                    time.sleep(2)
            
            print(f"Successfully uploaded {len(current_points)} points to Qdrant.")
            total_uploaded += len(current_points)
            if total_uploaded % 1000 == 0:
                print(f"Total uploaded points: {total_uploaded}", flush=True)
            print(f'Embedding_Queue length:{embedding_queue.qsize()}', flush=True)
        except Exception as e:
            print(f'Failed to upload points to Qdrant: {e}')
    
    print(f"Finished uploading all points. Total uploaded: {total_uploaded}", flush=True)






# ================ FILE PRODUCER THREAD CODE =========================
def file_producer_thread():
    # USED FOR DEBUGGING, MAY REMOVE OR ADD EXTRA LOCK IF MULTITHREADING
    global FINISHED_PRODUCERS

    # This will get all the directories in the local_path which will be each proceeding, now we iterate through each and add the batched files to the queue
    proceeding_count = 0
    current_chunks = []

    while not proceedings_queue.empty():
        try:
            proceeding = proceedings_queue.get_nowait()
            parseAllDocuments(proceeding, current_chunks)
            print(f"Finished processing {proceeding}, Proceeding {proceeding_count}", flush=True)
            proceeding_count += 1
        except Exception as e:
            print(f"Error processing proceeding {proceeding}: {e}", flush=True)
            continue # If queue is empty
    if current_chunks:
                chunks_queue.put(current_chunks.copy())
    
    # We will add None when Finished_producers 
    with finished_producers_lock:
        FINISHED_PRODUCERS += 1
        if FINISHED_PRODUCERS == NUM_PRODUCERS:
            # Add None to the queue to signal end of processing
            chunks_queue.put(None)
            print("Finished processing all producers. Signaling embedding thread to terminate.", flush=True)
    


# Function that parses all the documents in a proceeding directory and adds them to the queue
def parseAllDocuments(proceeding_directory: str, current_chunks: list):
    proceeding_directory = os.path.join(LOCAL_PATH, proceeding_directory)
    if not os.path.exists(proceeding_directory):
        print(f"Directory {proceeding_directory} does not exist.", flush=True)
        return
    
    metadata_file = os.path.join(proceeding_directory, 'metadata.json')
    if not os.path.exists(metadata_file):
        print(f"Metadata file {metadata_file} does not exist.", flush=True)
        return
    
    try:
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
    except Exception as e:
        print(f"Error loading metadata file {metadata_file}: {e}", flush=True)
        return
    
    for doc in metadata:
        if 'document_id' not in doc:
            print(f"Document {doc} does not have a document_id.", flush=True)
            continue

        pdf_path = os.path.join(proceeding_directory, doc['document_id'] + '.pdf')
        
        # check to see if document has been processed
        with seen_lock:
            if doc['document_id'] in seen:

                print(f"Document {doc['document_id']} already processed.", flush=True)
                continue
            seen.add(doc['document_id'])


        if not os.path.exists(pdf_path):
            print(f"PDF file {pdf_path} does not exist.", flush=True)
            continue
        
        try:
            # First we want to get the arguments for the document to pass to the embedding function so it can add the metadata to the queue
            doc_args = getDocArgs(doc)

            # Now we have to parse the docuemnt into chunks and add each chunk to the queue in batch sizes of BATCH_SIZE
            with open(pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            
            addChunksToQueue(pdf_bytes, doc_args, current_chunks)
        except Exception as e:
            print(f"Error processing document {doc['document_id']}: {e}")
            continue

# Takes in the bytes for pdf and adds chunks to queue in batches of BATCH_SIZE
def addChunksToQueue(pdf_bytes: bytes, doc_args: dict, current_chunks: list):
    try:
        pdf_file = BytesIO(pdf_bytes)
        pdf = fitz.open(stream=pdf_file, filetype='pdf')
        pdf_text = ''

        for page in pdf:
            pdf_text += page.get_text('text')
            pdf_text += '\n\n'
        
        pdf.close()
        
        # use overlap to create chunks
        text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP
            )

        chunks = text_splitter.split_text(pdf_text)


        # iterate through chunks and add them to the queue in batches of BATCH_SIZE
        for i,chunk in enumerate(chunks):
            # if empty skip
            if not chunk.strip():
                continue
            chunk_args = {
                **doc_args,
                'chunk_index': i,
                'text': chunk
            }
            current_chunks.append(chunk_args)

            if len(current_chunks) >= BATCH_SIZE:
                chunks_queue.put(current_chunks.copy())
                current_chunks.clear()  # Clear the current chunks after putting them in the queue
        DOCUMENT_COUNT += 1
        print(f"processed Document: {doc_args['document_id']}, Total Processed: {DOCUMENT_COUNT}", flush=True)

    except Exception as e:
        print(f"Error creating chunks from PDF: {e}", flush=True)
        return

    


def getDocArgs(doc):

    doc_type = doc.get('doc_type', None)

    # we need to clean the doc_type to remove things like "E-filed"
    if doc_type and doc_type.startswith('E-Filed: '):
        doc_type = doc_type[9::]
    
    # Also we want to store the year to help with range searching rather than a string
    year = 0
    if 'filing_date' in doc and doc['filing_date'] and len(str(doc['filing_date'])) >= 4:
        try:
            year_str = str(doc['filing_date'])[-4:]
            year = int(year_str)
        except ValueError:
            print(f"Could not parse year from filing_date: {doc['filing_date']}")
            year = 0

    doc_args = {
        'document_id': doc['document_id'],
        'proceeding_id': doc['proceeding_id'],
        'source_url': doc['source_url'],
        'published_date': doc['published_date'],
        'year': year,
        'title': doc['title'],
        'doc_type': doc_type
    }

    return doc_args

# ================================================================



def createCollection(delete=False):
    # Create the collection if it doesn't exist
    collections = qdrant_client.get_collections()
    existing_collections = [collection.name for collection in collections.collections]

    if delete:
        print(f"Deleting existing collection: {COLLECTION_NAME}", flush=True)
        if COLLECTION_NAME in existing_collections:
            qdrant_client.delete_collection(COLLECTION_NAME)
    
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=384,
            distance=Distance.COSINE
        )
    )

if __name__ == "__main__":
    # We need to initialize the qdrant collection
    createCollection()
    # initialize proceeding queue
    generateProceedings()

    embedding_thread = threading.Thread(target=embedding_thread, daemon=True)
    upload_thread = threading.Thread(target=upload_thread, daemon=True)

    producer_threads = []
    for i in range(NUM_PRODUCERS):
        producer_thread = threading.Thread(target=file_producer_thread, daemon=True)
        producer_threads.append(producer_thread)
    
    for thread in producer_threads:
        thread.start()
    embedding_thread.start()
    upload_thread.start()

    for thread in producer_threads:
        thread.join()
    embedding_thread.join()
    upload_thread.join()    


