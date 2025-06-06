import os
import json
import glob
import logging
import requests
import concurrent.futures
import threading
import argparse
import time
from datetime import datetime
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from dotenv import load_dotenv
from PyPDF2 import PdfReader
import chromadb
from chromadb.config import Settings

# ------------------------------------------------------------------------------
# 0. CONFIGURATION & SETUP - Configure cache directories BEFORE importing ML libraries
# ------------------------------------------------------------------------------

# Configure cache directories to use Y: drive to avoid filling C: drive
# Set these BEFORE importing sentence_transformers to ensure they take effect
os.environ["HF_HOME"] = "Y:/Accenture/GRC/model_cache/huggingface"
os.environ["HUGGINGFACE_HUB_CACHE"] = "Y:/Accenture/GRC/model_cache/huggingface/hub"
os.environ["TRANSFORMERS_CACHE"] = "Y:/Accenture/GRC/model_cache/huggingface/transformers"
os.environ["SENTENCE_TRANSFORMERS_HOME"] = "Y:/Accenture/GRC/model_cache/sentence_transformers"
os.environ["TORCH_HOME"] = "Y:/Accenture/GRC/model_cache/torch"
os.environ["XDG_CACHE_HOME"] = "Y:/Accenture/GRC/model_cache"

# Create cache directories if they don't exist
cache_dirs = [
    "Y:/Accenture/GRC/model_cache/huggingface/hub",
    "Y:/Accenture/GRC/model_cache/huggingface/transformers", 
    "Y:/Accenture/GRC/model_cache/sentence_transformers",
    "Y:/Accenture/GRC/model_cache/torch"
]
for cache_dir in cache_dirs:
    os.makedirs(cache_dir, exist_ok=True)

# NOW import sentence_transformers after setting cache directories
from sentence_transformers import SentenceTransformer

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Environment & DB settings
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_DB   = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASS = os.getenv("POSTGRES_PASS")
CHROMA_HOST   = os.getenv("CHROMA_HOST")
CHROMA_PERSIST_DIR = "./chroma_db"

# Thread-safe printing
print_lock = threading.Lock()
def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)

# Default thread counts
MAX_PROCEEDING_THREADS = 5  # Number of proceedings to process in parallel
MAX_DOCUMENT_THREADS = 3    # Number of documents to process in parallel for each proceeding

# ------------------------------------------------------------------------------
# 1. DATABASE HELPERS
# ------------------------------------------------------------------------------
def get_postgres_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASS
    )

def parse_date_string(date_str: str):
    if not date_str or pd.isna(date_str): return None
    date_str = date_str.strip('"\'').strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d %B %Y", "%d-%b-%Y"]:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    try:
        from dateutil import parser
        return parser.parse(date_str).date()
    except Exception:
        logging.warning(f"Could not parse date: '{date_str}'")
        return None

def get_or_create_proceeding(conn, proceeding_number: str, description="Imported via pipeline") -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM proceedings WHERE proceeding_number = %s", (proceeding_number,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            """INSERT INTO proceedings (proceeding_number, description, industry, current_status, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (proceeding_number, description, "Unknown", "Active", datetime.now(), datetime.now())
        )
        conn.commit()
        return cur.fetchone()[0]

def insert_document_record(conn, proceeding_id: int, doc_title: str, doc_content: str, doc_metadata: dict) -> int:
    with conn.cursor() as cur:
        pdf_url = doc_metadata.get("source_url", "")
        filed_by = doc_metadata.get("filed_by", "Unknown")
        # Truncate to roughly 100 characters if needed
        doc_type = (doc_metadata.get("doc_type", "DOCUMENT"))[:100]
        filing_date = doc_metadata.get("filing_date", datetime.now().date())
        cur.execute("SELECT id FROM documents WHERE pdf_url = %s", (pdf_url,))
        if cur.fetchone():
            logging.info(f"Document with URL {pdf_url} exists.")
            return cur.fetchone()[0]
        try:
            cur.execute(
                """INSERT INTO documents (proceeding_id, doc_type, filing_date, filed_by, description, pdf_url, doc_text)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (proceeding_id, doc_type, filing_date, filed_by, doc_title, pdf_url, doc_content)
            )
            doc_id = cur.fetchone()[0]
            conn.commit()
            return doc_id
        except psycopg2.errors.StringDataRightTruncation as e:
            conn.rollback()
            pdf_url = pdf_url[:250]
            filed_by = filed_by[:100]
            cur.execute(
                """INSERT INTO documents (proceeding_id, doc_type, filing_date, filed_by, description, pdf_url, doc_text)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (proceeding_id, doc_type, filing_date, filed_by, doc_title, pdf_url, doc_content)
            )
            doc_id = cur.fetchone()[0]
            conn.commit()
            return doc_id
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur.execute("SELECT id FROM documents WHERE pdf_url = %s", (pdf_url,))
            return cur.fetchone()[0]
        except Exception as e:
            conn.rollback()
            logging.error(f"Error inserting document: {e}")
            raise

def create_doc_chunks_table_if_not_exists(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS doc_chunks (
                id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
                chunk_text TEXT,
                chunk_metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
    conn.commit()

def bulk_insert_doc_chunks(conn, doc_id: int, chunk_data: list):
    create_doc_chunks_table_if_not_exists(conn)
    with conn.cursor() as cur:
        values = [(doc_id, chunk["chunk_text"], json.dumps(chunk["chunk_metadata"])) for chunk in chunk_data]
        execute_values(cur, "INSERT INTO doc_chunks (document_id, chunk_text, chunk_metadata) VALUES %s", values)
    conn.commit()

# ------------------------------------------------------------------------------
# 2. CHROMA (VECTOR DB) HELPERS
# ------------------------------------------------------------------------------
def get_collection_name(collection_name=None, proceeding_number=None):
    if proceeding_number:
        safe = proceeding_number.replace(" ", "_").replace("-", "_").lower()
        return f"proceeding_{safe}"
    return collection_name or "grc_documents"

def get_chroma_client():
    if CHROMA_HOST:
        parsed = urlparse(CHROMA_HOST)
        return chromadb.HttpClient(host=parsed.hostname, port=parsed.port)
    logging.error("CHROMA_HOST not set.")
    return None

def get_chroma_collection(collection_name=None, proceeding_number=None):
    client = get_chroma_client()
    name = get_collection_name(collection_name, proceeding_number)
    return client.get_or_create_collection(name=name) if client else None

def insert_chunks_into_chroma(collection, chunk_data: list):
    if not chunk_data:
        logging.info("No chunks to insert into Chroma.")
        return
    try:
        existing = set(collection.get().get("ids", []))
    except Exception:
        existing = set()
    new_chunks = [c for c in chunk_data if c["id"] not in existing]
    if not new_chunks:
        logging.info("All chunks already exist in Chroma. Skipping insertion.")
        return
    try:
        collection.add(
            embeddings=[c["embedding"] for c in new_chunks],
            metadatas=[c["metadata"] for c in new_chunks],
            documents=[c["metadata"].get("text", "") for c in new_chunks],
            ids=[c["id"] for c in new_chunks]
        )
        logging.info(f"Added {len(new_chunks)} new chunks to Chroma.")
    except Exception as e:
        logging.error(f"Error adding embeddings to Chroma: {e}")

# ------------------------------------------------------------------------------
# 3. PDF FETCHING & EXTRACTION
# ------------------------------------------------------------------------------
def download_pdf(url: str, save_path: str) -> str:
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(r.content)
        logging.info(f"Saved PDF to {save_path}")
        return save_path
    except Exception as e:
        logging.error(f"Error downloading PDF: {e}")
        return ""

def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        reader = PdfReader(pdf_path)
        return "\n".join([page.extract_text() or "" for page in reader.pages])
    except Exception as e:
        logging.error(f"Error extracting text: {e}")
        return ""

def chunk_text(text: str, max_tokens: int = 500) -> list:
    words = text.split()
    return [" ".join(words[i:i+max_tokens]) for i in range(0, len(words), max_tokens)]

# ------------------------------------------------------------------------------
# 4. PIPELINE EXECUTION - THREADED VERSION
# ------------------------------------------------------------------------------

def process_documents_data_threaded(proceeding_id, num_threads=MAX_DOCUMENT_THREADS, force_reprocess=False):
    """Process all document types for a single proceeding with threading"""
    start_time = time.time()
    safe_print(f"Processing documents for proceeding {proceeding_id}")
    
    conn = get_postgres_connection()
    proc_id = get_or_create_proceeding(conn, proceeding_id, f"Auto-processed for {proceeding_id}")
    
    tabs = ["documents", "rulings", "decisions", "public_comments"]
    
    # Try to initialize the embedding model
    try:
        model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
    except Exception as e:
        safe_print(f"Error loading embedding model: {e}")
        model = None
    
    # Try to get Chroma collection
    try:
        coll = get_chroma_collection(proceeding_number=proceeding_id)
    except Exception as e:
        safe_print(f"Error getting Chroma collection: {e}")
        coll = None
    
    # Process each tab's documents
    for tab_name in tabs:
        csv_path = os.path.join("metadata", proceeding_id, f"{tab_name}.csv")
        if not os.path.exists(csv_path):
            continue
            
        safe_print(f"Processing {tab_name} for {proceeding_id}")
        
        try:
            # Read CSV file
            try:
                df = pd.read_csv(csv_path, encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding='cp1252')
                
            if df.empty:
                continue
                
            # Process each document in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = []
                
                for _, row in df.iterrows():
                    futures.append(executor.submit(
                        process_document_row, 
                        row=row, 
                        proc_id=proc_id, 
                        proceeding_id=proceeding_id, 
                        tab_name=tab_name, 
                        model=model, 
                        coll=coll,
                        force_reprocess=force_reprocess
                    ))
                
                # Wait for all tasks to complete and gather results
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    try:
                        # Get result or exception if raised
                        _ = future.result()
                    except Exception as e:
                        safe_print(f"Error processing document: {e}")
                    
                    # Print progress periodically
                    if (i + 1) % 10 == 0 or (i + 1) == len(futures):
                        safe_print(f"Progress for {proceeding_id} - {tab_name}: {i + 1}/{len(futures)} documents processed")
        
        except Exception as e:
            safe_print(f"Error processing {tab_name} for {proceeding_id}: {e}")
    
    conn.close()
    elapsed_time = time.time() - start_time
    safe_print(f"Completed processing {proceeding_id} in {elapsed_time:.2f} seconds")
    return proceeding_id

def process_document_row(row, proc_id, proceeding_id, tab_name, model, coll, force_reprocess=False):
    """Process a single document row from a CSV file"""
    try:
        conn = get_postgres_connection()
        
        doc_type = row.get('document_type', tab_name.upper().rstrip('S'))
        description = row.get('description', '')
        filed_by = row.get('filed_by', 'Unknown')
        pdf_link = row.get('doc_link', '')
        filing_date = parse_date_string(str(row.get('filing_date', ""))) or datetime.now().date()
        
        if pdf_link.startswith('http:'):
            pdf_link = pdf_link.replace('http:', 'https:', 1)
            
        doc_metadata = {
            "source_url": pdf_link, 
            "filed_by": filed_by, 
            "doc_type": doc_type, 
            "filing_date": filing_date, 
            "tab_name": tab_name
        }
        
        # Check if document exists and skip if not forcing reprocess
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM documents WHERE pdf_url = %s", (pdf_link,))
            doc_exists = cur.fetchone()
            if doc_exists and not force_reprocess:
                return None
        
        # Create text for metadata record
        doc_text = f"Metadata-only record for {description}"
        
        # Insert the document
        doc_id = insert_document_record(conn, proc_id, description, doc_text, doc_metadata)
        
        # Create a document chunk
        chunk_str = f"Document: {description}\nType: {doc_type}\nFiled By: {filed_by}\nFiling Date: {filing_date}"
        chunk_metadata = {
            "chunk_index": 0, 
            "document_id": doc_id, 
            "proceeding_id": proc_id,
            "proceeding_number": proceeding_id, 
            "source_url": pdf_link, 
            "document_type": doc_type,
            "filed_by": filed_by, 
            "tab_name": tab_name
        }
        
        # Insert the chunk
        bulk_insert_doc_chunks(conn, doc_id, [{"chunk_text": chunk_str, "chunk_metadata": chunk_metadata}])
        
        # Add to Chroma if model and collection available
        if model and coll:
            try:
                embedding = model.encode(chunk_str).tolist()
                chroma_chunk = {
                    "id": f"doc{doc_id}_chunk0",
                    "embedding": embedding,
                    "metadata": {
                        "document_id": doc_id, 
                        "proceeding_id": proc_id, 
                        "proceeding_number": proceeding_id,
                        "chunk_index": 0, 
                        "source_url": pdf_link, 
                        "text": chunk_str,
                        "document_type": doc_type, 
                        "filed_by": filed_by, 
                        "tab_name": tab_name
                    }
                }
                insert_chunks_into_chroma(coll, [chroma_chunk])
            except Exception as e:
                logging.error(f"Error adding to Chroma: {e}")
        
        conn.commit()
        conn.close()
        return doc_id
        
    except Exception as e:
        logging.error(f"Error processing document: {e}")
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        return None

def process_proceeding_metadata_threaded(proceeding_id):
    """Process metadata for a single proceeding"""
    try:
        conn = get_postgres_connection()
        proc_csv = os.path.join("metadata", proceeding_id, "proceeding.csv")
        
        if os.path.exists(proc_csv):
            try:
                df = pd.read_csv(proc_csv, encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(proc_csv, encoding='cp1252')
                
            if not df.empty:
                row = df.iloc[0]
                proc_num = row.get('proceeding_number', proceeding_id)
                filed_by = row.get('filed_by')
                industry = row.get('industry')
                filing_date = parse_date_string(str(row.get('filing_date', ""))) or datetime.now().date()
                category = row.get('category')
                current_status = row.get('current_status', 'Active')
                description = row.get('description')
                
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM proceedings WHERE proceeding_number = %s", (proc_num,))
                    if cur.fetchone():
                        cur.execute(
                            """UPDATE proceedings SET filed_by=%s, industry=%s, filing_date=%s, category=%s,
                               current_status=%s, description=%s, updated_at=%s WHERE proceeding_number = %s RETURNING id""",
                            (filed_by, industry, filing_date, category, current_status, description, datetime.now(), proc_num)
                        )
                    else:
                        cur.execute(
                            """INSERT INTO proceedings (proceeding_number, filed_by, industry, filing_date, category,
                               current_status, description, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                               RETURNING id""",
                            (proc_num, filed_by, industry, filing_date, category, current_status, description, datetime.now(), datetime.now())
                        )
                conn.commit()
        else:
            # Create a basic proceeding entry if no CSV exists
            get_or_create_proceeding(conn, proceeding_id, f"Auto-created for {proceeding_id}")
            
        conn.close()
        return proceeding_id
    except Exception as e:
        logging.error(f"Error processing proceeding metadata for {proceeding_id}: {e}")
        return None

def run_threaded_pipeline(max_workers=MAX_PROCEEDING_THREADS, doc_workers=MAX_DOCUMENT_THREADS):
    """
    Run the pipeline with threading for faster processing
    """
    logging.info("Starting threaded metadata extraction pipeline...")
    
    # Find all proceeding folders
    metadata_path = "metadata"
    if not os.path.exists(metadata_path):
        logging.error(f"Metadata directory '{metadata_path}' does not exist")
        return
        
    folders = [os.path.basename(f) for f in glob.glob(f"{metadata_path}/*") if os.path.isdir(f)]
    if not folders:
        logging.error("No proceeding folders found in metadata directory")
        return
        
    start_time = time.time()
    logging.info(f"Found {len(folders)} proceedings to process")
    
    # Process proceeding metadata first
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        safe_print(f"Processing proceeding metadata using {max_workers} threads")
        futures = [executor.submit(process_proceeding_metadata_threaded, proc_id) for proc_id in folders]
        
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            try:
                proc_id = future.result()
                if proc_id:
                    if (i + 1) % 10 == 0 or (i + 1) == len(futures):
                        safe_print(f"Metadata progress: {i + 1}/{len(futures)} proceedings processed")
            except Exception as e:
                safe_print(f"Error processing proceeding metadata: {e}")
    
    # Process documents for each proceeding
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        safe_print(f"Processing documents using {max_workers} proceeding threads and {doc_workers} document threads per proceeding")
        futures = [executor.submit(process_documents_data_threaded, proc_id, doc_workers) for proc_id in folders]
        
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            try:
                proc_id = future.result()
                if proc_id:
                    if (i + 1) % 5 == 0 or (i + 1) == len(futures):
                        safe_print(f"Document processing progress: {i + 1}/{len(futures)} proceedings completed")
            except Exception as e:
                safe_print(f"Error processing proceeding documents: {e}")
    
    elapsed_time = time.time() - start_time
    safe_print(f"Threaded pipeline completed in {elapsed_time:.2f} seconds")
    safe_print(f"Average time per proceeding: {elapsed_time/len(folders):.2f} seconds")
    
    logging.info("Threaded metadata extraction pipeline completed.")

# ------------------------------------------------------------------------------
# 5. MAIN EXECUTION
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Threaded GRC Document Pipeline")
    parser.add_argument("--proc-threads", type=int, default=MAX_PROCEEDING_THREADS, 
                        help=f"Number of proceeding threads (default: {MAX_PROCEEDING_THREADS})")
    parser.add_argument("--doc-threads", type=int, default=MAX_DOCUMENT_THREADS,
                        help=f"Number of document threads per proceeding (default: {MAX_DOCUMENT_THREADS})")
    args = parser.parse_args()
    
    run_threaded_pipeline(max_workers=args.proc_threads, doc_workers=args.doc_threads) 