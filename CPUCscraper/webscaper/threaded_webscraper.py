import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import os
import csv
import re
import concurrent.futures
import threading
import queue
import argparse
import sys

# Thread-safe printing
print_lock = threading.Lock()
def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)

# Constants
REQUEST_TIMEOUT = 30  # sec
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
MAX_WORKERS = 5  # Number of parallel workers for processing proceedings
DOC_WORKERS = 3  # Number of workers for processing document links

# Create directories if they don't exist
#MOVE THIS INTO THE WEBSCRAPER DIRECTORY
os.makedirs("proceeding_links", exist_ok=True)
os.makedirs("metadata", exist_ok=True)

def get_apex_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    search_url = "https://apps.cpuc.ca.gov/apex/f?p=401:5::::RP,5,RIR,57,RIR::"
    safe_print("Initializing base session:", search_url)
    try:
        resp = session.get(search_url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            safe_print(f"Error: {resp.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        safe_print(f"Error: {e}")
        return None

    safe_print("Session initialized")
    return session

def load_proceeding_ids_from_file(file_path="proceeding_ids.txt"):
    try:
        if not os.path.exists(file_path):
            safe_print(f"Error: File {file_path} not found.")
            return []
            
        with open(file_path, 'r') as f:
            proceeding_ids = [line.strip() for line in f if line.strip()]
            
        safe_print(f"Loaded {len(proceeding_ids)} proceeding IDs from {file_path}")
        return proceeding_ids
    except Exception as e:
        safe_print(f"Error loading proceeding IDs from file: {e}")
        return []

def parse_tabs_from_proceeding(session_apex, proceeding_id):
    detail_url = "https://apps.cpuc.ca.gov/apex/f"
    params = {
        "p": f"401:56::::RP,57,RIR:P5_PROCEEDING_SELECT:{proceeding_id}"
    }
    safe_print(f"\nProcessing: {proceeding_id}")
    
    try:
        resp = session_apex.get(detail_url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            safe_print(f"Error: {proceeding_id} (status={resp.status_code})")
            return {}, None
    except requests.exceptions.RequestException as e:
        safe_print(f"Error: {e}")
        return {}, None

    soup = BeautifulSoup(resp.text, "html.parser")

    proceeding_metadata = {
        'proceeding_number': proceeding_id,
        'filed_by': '',
        'service_lists': '',
        'industry': '',
        'filing_date': '',
        'category': '',
        'current_status': '',
        'description': '',
        'staff': ''
    }

    # Extract metadata from the page
    if not any(value for key, value in proceeding_metadata.items() if key != 'proceeding_number'):
        title_element = soup.find('span', {'id': 'P56_PROCEEDING_TITLE_DISPLAY'})
        if title_element:
            title_text = title_element.get_text(strip=True)
            if " - " in title_text:
                parts = title_text.split(" - ", 1)
                if len(parts) == 2:
                    proceeding_metadata['description'] = parts[1]

        page_text = soup.get_text()

        # Filed By
        filed_by_match = re.search(r'Filed By:\s*([^\n]+)', page_text)
        if filed_by_match:
            filed_by_text = filed_by_match.group(1).strip()
            if "Service Lists:" in filed_by_text:
                filed_by_text = filed_by_text.split("Service Lists:")[0].strip()
            proceeding_metadata['filed_by'] = filed_by_text

        # Service Lists 
        service_lists_match = re.search(r'Service Lists:\s*([^\n]+?)(?=Industry:|$)', page_text)
        if service_lists_match:
            proceeding_metadata['service_lists'] = service_lists_match.group(1).strip()

        # Industry 
        industry_match = re.search(r'Industry:\s*([^\n]+?)(?=Filing Date:|$)', page_text)
        if industry_match:
            proceeding_metadata['industry'] = industry_match.group(1).strip()

        # Filing Date 
        filing_date_match = re.search(r'Filing Date:\s*([^\n]+?)(?=Category:|$)', page_text)
        if filing_date_match:
            proceeding_metadata['filing_date'] = filing_date_match.group(1).strip()

        # Category
        category_match = re.search(r'Category:\s*([^\n]+?)(?=Current Status:|$)', page_text)
        if category_match:
            proceeding_metadata['category'] = category_match.group(1).strip()

        # Current Status 
        status_match = re.search(r'Current Status:\s*([^\n]+?)(?=Description:|$)', page_text)
        if status_match:
            proceeding_metadata['current_status'] = status_match.group(1).strip()

        # Description 
        desc_match = re.search(r'Description:\s*([^\n]+?)(?=Staff:|$)', page_text)
        if desc_match:
            proceeding_metadata['description'] = desc_match.group(1).strip()

        # Staff 
        staff_match = re.search(r'Staff:\s*([^\n]+)', page_text)
        if staff_match:
            proceeding_metadata['staff'] = staff_match.group(1).strip()

    # Find tab links
    tabs_ul = soup.select_one("div.sHorizontalTabsInner ul")
    if not tabs_ul:
        safe_print(f"No tabs found for {proceeding_id}")
        return {}, proceeding_metadata

    tab_links = {}
    for li in tabs_ul.find_all("li"):
        a_tag = li.find("a")
        if a_tag:
            title = a_tag.get_text(strip=True)
            href = a_tag.get("href")
            full_url = urljoin("https://apps.cpuc.ca.gov/apex/", href)
            tab_links[title] = full_url

    return tab_links, proceeding_metadata

def clean_field_value(value):
    if not value or not isinstance(value, str):
        return value
    
    headers = [
        "Service Lists:", "Industry:", "Filing Date:", 
        "Category:", "Current Status:", "Description:", "Staff:"
    ]
    
    cleaned_value = value
    for header in headers:
        if header in cleaned_value:
            parts = cleaned_value.split(header)
            if len(parts) > 1:
                if parts[0].strip():
                    cleaned_value = parts[0].strip()
                else:
                    next_part = parts[1]
                    for h in headers:
                        if h in next_part:
                            next_part = next_part.split(h)[0].strip()
                            break
                    cleaned_value = next_part.strip()
    
    return cleaned_value

def extract_document_links_from_tab(session_apex, doc_tab_url, tab_name):
    try:
        resp = session_apex.get(doc_tab_url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            safe_print(f"Error retrieving tab page: {doc_tab_url} (status={resp.status_code})")
            return [], []
    except requests.exceptions.RequestException as e:
        safe_print(f"Error: {e}")
        return [], []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Check for interactive report table
    table = soup.select_one("table.a-IRR-table")
    if not table:
        no_data_div = soup.select_one("div.a-IRR-noDataMsg")
        if no_data_div:
            msg = no_data_div.get_text(strip=True)
            safe_print(f"No data: {msg}")
        else:
            safe_print(f"No interactive report table found for tab {tab_name}")
        return [], []

    rows = table.select("tr")[1:]
    doc_links = []
    doc_metadata_list = []

    for row in rows:
        cells = row.select("td.u-tL")
        doc_metadata = {
            'filing_date': '',
            'document_type': '',
            'filed_by': '',
            'description': '',
            'doc_link': ''
        }
        
        # Handle different tab types
        if tab_name == "Documents" and len(cells) >= 4:
            if cells[0]:
                doc_metadata['filing_date'] = clean_field_value(cells[0].get_text(strip=True))
            
            if cells[1]:
                doc_metadata['document_type'] = clean_field_value(cells[1].get_text(strip=True))
                
                link_tag = cells[1].find("a")
                if link_tag and link_tag.get("href", ""):
                    doc_link = link_tag["href"]
                    if doc_link.startswith("http://"):
                        doc_link = doc_link.replace("http://", "https://")
                    doc_links.append(doc_link)
                    doc_metadata['doc_link'] = doc_link
            
            if cells[2]:
                doc_metadata['filed_by'] = clean_field_value(cells[2].get_text(strip=True))
            
            if cells[3]:
                doc_metadata['description'] = clean_field_value(cells[3].get_text(strip=True))
                
        elif tab_name == "Rulings" and len(cells) >= 3:
            if cells[0]:
                doc_metadata['filing_date'] = clean_field_value(cells[0].get_text(strip=True))
            
            if cells[1]:
                doc_metadata['document_type'] = "RULING"
                
                ruling_text = cells[1].get_text(strip=True)
                doc_metadata['description'] = clean_field_value(ruling_text)
                
                link_tag = cells[1].find("a")
                if link_tag and link_tag.get("href", ""):
                    doc_link = link_tag["href"]
                    if doc_link.startswith("http://"):
                        doc_link = doc_link.replace("http://", "https://")
                    doc_links.append(doc_link)
                    doc_metadata['doc_link'] = doc_link
            
            if len(cells) >= 3 and cells[2]:
                doc_metadata['filed_by'] = clean_field_value(cells[2].get_text(strip=True))
            
            if len(cells) >= 4 and cells[3]:
                additional_desc = clean_field_value(cells[3].get_text(strip=True))
                if additional_desc:
                    if doc_metadata['description']:
                        doc_metadata['description'] += " - " + additional_desc
                    else:
                        doc_metadata['description'] = additional_desc
                
        elif tab_name == "Decisions" and len(cells) >= 5:
            if cells[0]:
                doc_metadata['filing_date'] = clean_field_value(cells[0].get_text(strip=True))
                doc_metadata['adopted_filed_date'] = doc_metadata['filing_date']
            
            if cells[1]:
                doc_metadata['effective_date'] = clean_field_value(cells[1].get_text(strip=True))
                
            if cells[2]:
                doc_metadata['issued_date'] = clean_field_value(cells[2].get_text(strip=True))
            
            if cells[3]:
                doc_metadata['document_type'] = "DECISION"
                
                link_tag = cells[3].find("a")
                if link_tag and link_tag.get("href", ""):
                    doc_link = link_tag["href"]
                    if doc_link.startswith("http://"):
                        doc_link = doc_link.replace("http://", "https://")
                    doc_links.append(doc_link)
                    doc_metadata['doc_link'] = doc_link
                    
                    link_text = link_tag.get_text(strip=True)
                    if link_text:
                        doc_metadata['document_type_text'] = clean_field_value(link_text)
                else:
                    doc_type_text = cells[3].get_text(strip=True)
                    if doc_type_text:
                        doc_metadata['document_type_text'] = clean_field_value(doc_type_text)
            
            if cells[4]:
                doc_metadata['description'] = clean_field_value(cells[4].get_text(strip=True))
                
            doc_metadata['filed_by'] = "CPUC"
                
        elif tab_name == "Decisions" and len(cells) >= 4:
            if cells[0]:
                doc_metadata['filing_date'] = clean_field_value(cells[0].get_text(strip=True))
                doc_metadata['adopted_filed_date'] = doc_metadata['filing_date']
            
            if cells[1]:
                doc_metadata['effective_date'] = clean_field_value(cells[1].get_text(strip=True))
            
            if cells[2]:
                doc_metadata['document_type'] = "DECISION"
                
                link_tag = cells[2].find("a")
                if link_tag and link_tag.get("href", ""):
                    doc_link = link_tag["href"]
                    if doc_link.startswith("http://"):
                        doc_link = doc_link.replace("http://", "https://")
                    doc_links.append(doc_link)
                    doc_metadata['doc_link'] = doc_link
                    
                    link_text = link_tag.get_text(strip=True)
                    if link_text:
                        doc_metadata['document_type_text'] = clean_field_value(link_text)
                else:
                    doc_type_text = cells[2].get_text(strip=True)
                    if doc_type_text:
                        doc_metadata['document_type_text'] = clean_field_value(doc_type_text)
            
            if cells[3]:
                doc_metadata['description'] = clean_field_value(cells[3].get_text(strip=True))
                
            doc_metadata['filed_by'] = "CPUC"
                
        elif tab_name == "Public Comments" and len(cells) >= 3:
            if cells[0]:
                doc_metadata['filing_date'] = clean_field_value(cells[0].get_text(strip=True))
            
            if cells[1]:
                doc_metadata['document_type'] = "PUBLIC COMMENT"
                
                comment_text = cells[1].get_text(strip=True)
                doc_metadata['description'] = clean_field_value(comment_text)
                
                link_tag = cells[1].find("a")
                if link_tag and link_tag.get("href", ""):
                    doc_link = link_tag["href"]
                    if doc_link.startswith("http://"):
                        doc_link = doc_link.replace("http://", "https://")
                    doc_links.append(doc_link)
                    doc_metadata['doc_link'] = doc_link
            
            if cells[2]:
                doc_metadata['filed_by'] = clean_field_value(cells[2].get_text(strip=True))

        # Add metadata if link exists
        if doc_metadata['doc_link']:
            doc_metadata_list.append(doc_metadata)

    return doc_links, doc_metadata_list

def collect_pdf_links(doc_link):
    session_docs = requests.Session()
    session_docs.headers.update({"User-Agent": USER_AGENT})

    try:
        resp = session_docs.get(doc_link, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            safe_print(f"Error retrieving doc page at {doc_link} (status={resp.status_code})")
            return []
    except requests.exceptions.RequestException as e:
        safe_print(f"Error - request to {doc_link} failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    doc_urls = []

    content_area = soup.select_one("div#divDocContent")
    if content_area:
        for a_tag in content_area.find_all("a"):
            href = a_tag.get("href", "").strip()
            if href and not href.startswith("#") and not href.startswith("javascript:"):
                if href.startswith("http://"):
                    href = href.replace("http://", "https://")
                full_url = urljoin(doc_link, href)
                doc_urls.append((full_url, a_tag.get_text(strip=True) or "Unnamed Document"))
    else:
        for a_tag in soup.find_all("a"):
            href = a_tag.get("href", "").strip()
            if (href.lower().endswith(".pdf") or
                "PublishedDocs" in href or
                "SearchRes.aspx" in href):
                if href.startswith("http://"):
                    href = href.replace("http://", "https://")
                full_url = urljoin(doc_link, href)
                doc_urls.append((full_url, a_tag.get_text(strip=True) or "Unnamed Document"))

    return doc_urls

def save_links_to_file(proceeding_id, tab_name, links):
    os.makedirs(f"proceeding_links/{proceeding_id}", exist_ok=True)
    filename = f"proceeding_links/{proceeding_id}/{tab_name}.txt"

    with open(filename, "w") as f:
        f.write(f"{proceeding_id}\n")
        for i, (url, name) in enumerate(links):
            f.write(f"{url}\n")

    safe_print(f"Saved {len(links)} links to {filename}")

def process_document_links(proceeding_id, tab_name, doc_links, doc_metadata_list, doc_thread_count):
    """Process documents links using a thread pool"""
    all_document_links = []
    doc_queue = queue.Queue()
    
    # Add all document links to the queue
    for doc_link in doc_links:
        doc_queue.put(doc_link)
    
    # Process documents in parallel - use thread count parameter
    with concurrent.futures.ThreadPoolExecutor(max_workers=doc_thread_count) as executor:
        # Function for workers to process documents
        def process_doc_worker():
            while True:
                try:
                    doc_link = doc_queue.get_nowait()
                except queue.Empty:
                    break
                
                try:
                    document_links = collect_pdf_links(doc_link)
                    if document_links:
                        with print_lock:
                            all_document_links.extend(document_links)
                    time.sleep(0.2)  # Small delay to avoid hitting server too hard
                except Exception as e:
                    safe_print(f"Error processing document {doc_link}: {e}")
                finally:
                    doc_queue.task_done()
        
        # Start workers
        workers = []
        for _ in range(min(doc_thread_count, doc_queue.qsize())):
            worker = executor.submit(process_doc_worker)
            workers.append(worker)
        
        # Wait for all tasks to complete
        for worker in workers:
            worker.result()
    
    # If document links were found, save them
    if all_document_links:
        save_links_to_file(proceeding_id, tab_name, all_document_links)
        return all_document_links
    else:
        safe_print(f"No document links found in {tab_name} tab for {proceeding_id}")
        return []

def process_proceeding(session_apex, proc_id, doc_thread_count):
    """Process a single proceeding - called by worker threads"""
    try:
        safe_print(f"\n--- Starting processing for proceeding: {proc_id} ---")
        
        # Parse tabs and metadata
        tabs_data, proceeding_metadata = parse_tabs_from_proceeding(session_apex, proc_id)
        
        if not proceeding_metadata:
            safe_print(f"Failed to extract metadata for {proc_id}")
            return
        
        # Tabs to process
        tabs_to_process = {
            "Documents": tabs_data.get("Documents"),
            "Rulings": tabs_data.get("Rulings"),
            "Decisions": tabs_data.get("Decisions"),
            "Public Comments": tabs_data.get("Public Comments")
        }
        
        # Store metadata for each tab type separately
        tab_metadata = {
            "Documents": [],
            "Rulings": [],
            "Decisions": [],
            "Public Comments": []
        }
        
        for tab_name, tab_url in tabs_to_process.items():
            if not tab_url:
                safe_print(f"No '{tab_name}' tab found for {proc_id}")
                continue
                
            safe_print(f"Processing {proc_id} - {tab_name} tab")
            
            # Extract document links from the tab
            doc_links, doc_metadata_list = extract_document_links_from_tab(session_apex, tab_url, tab_name)
            
            if not doc_links:
                safe_print(f"No document links found in {tab_name} tab for {proc_id}")
                continue
                
            safe_print(f"Found {len(doc_links)} document links in {tab_name} tab for {proc_id}")
            
            # Add metadata
            if doc_metadata_list:
                for metadata in doc_metadata_list:
                    metadata['proceeding_id'] = proc_id
                    metadata['tab_name'] = tab_name
                    tab_metadata[tab_name].append(metadata)
            
            # Process document links in parallel
            process_document_links(proc_id, tab_name, doc_links, doc_metadata_list, doc_thread_count)
        
        # Save all metadata to CSV
        if proceeding_metadata:
            os.makedirs(f"metadata/{proc_id}", exist_ok=True)
            
            # Save proceeding metadata
            proceeding_file = f"metadata/{proc_id}/proceeding.csv"
            with open(proceeding_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=proceeding_metadata.keys())
                writer.writeheader()
                writer.writerow(proceeding_metadata)
            safe_print(f"Saved proceeding metadata to {proceeding_file}")
        
        # Save document metadata for each tab type separately
        for tab_name, metadata_list in tab_metadata.items():
            if metadata_list:
                tab_file = tab_name.lower().replace(" ", "_")
                metadata_file = f"metadata/{proc_id}/{tab_file}.csv"
                
                with open(metadata_file, 'w', encoding='utf-8', newline='') as f:
                    try:
                        writer = csv.DictWriter(f, fieldnames=metadata_list[0].keys())
                        writer.writeheader()
                        writer.writerows(metadata_list)
                    except Exception as e:
                        safe_print(f"Error saving metadata: {e}")
                safe_print(f"Saved {len(metadata_list)} {tab_name} metadata entries to {metadata_file}")
        
        safe_print(f"--- Completed processing for proceeding: {proc_id} ---")
    except Exception as e:
        safe_print(f"Error processing proceeding {proc_id}: {e}")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Threaded webscraper for CPUC proceedings")
    parser.add_argument("--threads", type=int, default=MAX_WORKERS, 
                        help=f"Number of worker threads (default: {MAX_WORKERS})")
    parser.add_argument("--doc-threads", type=int, default=DOC_WORKERS,
                        help=f"Number of document worker threads (default: {DOC_WORKERS})")
    parser.add_argument("--file", type=str, default="proceeding_ids.txt",
                        help="File containing proceeding IDs to process")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit the number of proceedings to process (0 = no limit)")
    args = parser.parse_args()
    
    # Get thread counts from arguments
    proc_thread_count = args.threads
    doc_thread_count = args.doc_threads
    
    # Initialize session
    session_apex = get_apex_session()
    if not session_apex:
        safe_print("Failed to initialize session")
        return 1
    
    # Load proceeding IDs
    proceeding_ids = load_proceeding_ids_from_file(args.file)
    if not proceeding_ids:
        safe_print("Warning: No proceeding IDs found in file. Using a small sample set instead.")
        proceeding_ids = ["A2502016", "C2502006", "C2502003", "A2502011", "C2502019"]
    
    # Apply limit if specified
    if args.limit > 0 and args.limit < len(proceeding_ids):
        safe_print(f"Limiting to first {args.limit} proceedings")
        proceeding_ids = proceeding_ids[:args.limit]
    
    # Display stats
    safe_print(f"Processing {len(proceeding_ids)} proceedings using {proc_thread_count} worker threads")
    safe_print(f"Using {doc_thread_count} threads per proceeding for document processing")
    
    # Process in parallel using ThreadPoolExecutor
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=proc_thread_count) as executor:
        futures = []
        for proc_id in proceeding_ids:
            # Create a new session for each thread to avoid conflicts
            thread_session = get_apex_session()
            if thread_session:
                future = executor.submit(process_proceeding, thread_session, proc_id, doc_thread_count)
                futures.append(future)
        
        # Wait for all tasks to complete
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            try:
                # Get the result (or exception if raised)
                future.result()
            except Exception as e:
                safe_print(f"Error in worker thread: {e}")
            
            # Print progress periodically
            if (i + 1) % 5 == 0 or (i + 1) == len(futures):
                safe_print(f"Progress: {i + 1}/{len(futures)} proceedings completed")
    
    # Display completion stats
    elapsed_time = time.time() - start_time
    safe_print(f"\nProcessing completed in {elapsed_time:.2f} seconds")
    safe_print(f"Average time per proceeding: {elapsed_time/len(proceeding_ids):.2f} seconds")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 