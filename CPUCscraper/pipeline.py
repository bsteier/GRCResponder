import os, json, glob, logging, requests
from datetime import datetime
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from dotenv import load_dotenv
from PyPDF2 import PdfReader
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# ------------------------------------------------------------------------------
# 0. CONFIGURATION & SETUP
# ------------------------------------------------------------------------------
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
# 4. PIPELINE EXECUTION
# ------------------------------------------------------------------------------
def run_ingestion_pipeline(pdf_url: str, proceeding_number="DEFAULT-PROC-001", force_reprocess=False, delete_existing_chunks=False):
    local_pdf = "sample_grc.pdf"
    if not download_pdf(pdf_url, local_pdf): return
    full_text = extract_text_from_pdf(local_pdf)
    if not full_text.strip(): return

    conn = get_postgres_connection()
    proc_id = get_or_create_proceeding(conn, proceeding_number)
    doc_metadata = {
        "source_url": pdf_url,
        "file_name": os.path.basename(local_pdf),
        "doc_type": "APPLICATION",
        "filed_by": "Pipeline Import",
        "filing_date": datetime.now().date()
    }
    doc_title = "Sample GRC Document"
    doc_id = insert_document_record(conn, proc_id, doc_title, full_text, doc_metadata)

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM doc_chunks WHERE document_id = %s", (doc_id,))
        if cur.fetchone()[0] > 0 and not force_reprocess:
            logging.info(f"Document {doc_id} already processed. Skipping.")
            conn.close()
            return

    if force_reprocess and delete_existing_chunks:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM doc_chunks WHERE document_id = %s", (doc_id,))
        conn.commit()
        try:
            coll = get_chroma_collection(proceeding_number=proceeding_number)
            results = coll.get(where={"document_id": doc_id})
            if results.get("ids"):
                coll.delete(ids=results["ids"])
        except Exception as e:
            logging.warning(f"Error deleting chunks from Chroma: {e}")

    chunks = chunk_text(full_text)
    print(f"chunks generated:\n {chunks}")
    doc_chunks = [{"chunk_text": chunk, "chunk_metadata": {"chunk_index": i}} for i, chunk in enumerate(chunks)]
    bulk_insert_doc_chunks(conn, doc_id, doc_chunks)

    model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
    chroma_chunks = []
    for i, chunk in enumerate(doc_chunks):
        embedding = model.encode(chunk["chunk_text"]).tolist()
        chroma_chunks.append({
            "id": f"doc{doc_id}_chunk{i}",
            "embedding": embedding,
            "metadata": {
                "document_id": doc_id,
                "proceeding_id": proc_id,
                "proceeding_number": proceeding_number,
                "chunk_index": i,
                "source_url": pdf_url,
                "text": chunk["chunk_text"]
            }
        })
    coll = get_chroma_collection(proceeding_number=proceeding_number)
    if coll: insert_chunks_into_chroma(coll, chroma_chunks)
    conn.close()

def process_proceeding_metadata_folders():
    conn = get_postgres_connection()
    metadata_path = "webscraper/metadata"
    folders = glob.glob(f"{metadata_path}/*") or glob.glob("webscaper/metadata/*")
    for folder in folders:
        proc_num = os.path.basename(folder)
        proc_csv = os.path.join(folder, "proceeding.csv")
        if os.path.exists(proc_csv):
            process_proceeding_data(conn, proc_csv, proc_num)
        else:
            get_or_create_proceeding(conn, proc_num, f"Auto-created for {proc_num}")
        for fname, tab in [("documents.csv", "Documents"),
                           ("rulings.csv", "Rulings"),
                           ("decisions.csv", "Decisions"),
                           ("public_comments.csv", "Public Comments")]:
            csv_path = os.path.join(folder, fname)
            if os.path.exists(csv_path):
                process_documents_data(conn, csv_path, proc_num, tab)
        try:
            get_chroma_collection(proceeding_number=proc_num)
        except Exception as e:
            logging.error(f"Chroma error for {proc_num}: {e}")
    conn.close()

def process_proceeding_data(conn, csv_path, proceeding_id):
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding='cp1252')
    if df.empty: return
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

def process_documents_data(conn, csv_path, proceeding_id, tab_name="Documents"):
    df = pd.read_csv(csv_path)
    if df.empty: return
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM proceedings WHERE proceeding_number = %s", (proceeding_id,))
        row = cur.fetchone()
        proc_id = row[0] if row else get_or_create_proceeding(conn, proceeding_id, f"Auto-created for {proceeding_id}")
    try:
        model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
    except Exception as e:
        logging.error(f"Embedding model load error: {e}")
        model = None
    try:
        coll = get_chroma_collection(proceeding_number=proceeding_id)
    except Exception:
        coll = None
    chroma_chunks = []
    for _, row in df.iterrows():
        doc_type = row.get('document_type', tab_name.upper())
        description = row.get('description', '')
        filed_by = row.get('filed_by', 'Unknown')
        pdf_link = row.get('doc_link', '')
        filing_date = parse_date_string(str(row.get('filing_date', ""))) or datetime.now().date()
        if pdf_link.startswith('http:'):
            pdf_link = pdf_link.replace('http:', 'https:', 1)
        doc_metadata = {"source_url": pdf_link, "filed_by": filed_by, "doc_type": doc_type, "filing_date": filing_date, "tab_name": tab_name}
        doc_text = f"Metadata-only record for {description}"
        try:
            doc_id = insert_document_record(conn, proc_id, description, doc_text, doc_metadata)
            chunk_str = f"Document: {description}\nType: {doc_type}\nFiled By: {filed_by}\nFiling Date: {filing_date}"
            bulk_insert_doc_chunks(conn, doc_id, [{"chunk_text": chunk_str, "chunk_metadata": {
                "chunk_index": 0, "document_id": doc_id, "proceeding_id": proc_id,
                "proceeding_number": proceeding_id, "source_url": pdf_link, "document_type": doc_type,
                "filed_by": filed_by, "tab_name": tab_name
            }}])
            if model and coll:
                embedding = model.encode(chunk_str).tolist()
                chroma_chunks.append({
                    "id": f"doc{doc_id}_chunk0",
                    "embedding": embedding,
                    "metadata": {
                        "document_id": doc_id, "proceeding_id": proc_id, "proceeding_number": proceeding_id,
                        "chunk_index": 0, "source_url": pdf_link, "text": chunk_str,
                        "document_type": doc_type, "filed_by": filed_by, "tab_name": tab_name
                    }
                })
        except Exception as e:
            logging.error(f"Error processing document: {e}")
    if chroma_chunks and coll:
        insert_chunks_into_chroma(coll, chroma_chunks)
    conn.commit()

def run_metadata_extraction_pipeline():
    logging.info("Starting metadata extraction pipeline...")
    process_proceeding_metadata_folders()
    logging.info("Metadata extraction pipeline completed.")

# ------------------------------------------------------------------------------
# 5. MAIN EXECUTION
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    run_metadata_extraction_pipeline()
    # Example: run_ingestion_pipeline(pdf_url="https://docs.cpuc.ca.gov/PublishedDocs/Efile/G000/M546/K561/546561410.PDF")
