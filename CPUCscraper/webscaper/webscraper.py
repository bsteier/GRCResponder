import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import os
import csv
import re

REQUEST_TIMEOUT = 30  #sec

#THIS IS NECESSSARRY - OTHERWISE SESSION EXPIRRES
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def get_apex_session():

    session = requests.Session()
    # simulates real browser
    session.headers.update({"User-Agent": USER_AGENT})

    # 1) this is default landing page - contains all proceedingfs
    search_url = "https://apps.cpuc.ca.gov/apex/f?p=401:5::::RP,5,RIR,57,RIR::"
    print("base session:", search_url)
    try:
        resp = session.get(search_url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print("error".format(resp.status_code))
            return None
    except requests.exceptions.RequestException as e:
        print(f"error {e}")
        return None

    print("initialized")
    return session

# Function to load proceeding IDs from file
def load_proceeding_ids_from_file(file_path="proceeding_ids.txt"):
    """
    Load proceeding IDs from a text file.
    Each ID should be on a separate line.
    """
    try:
        if not os.path.exists(file_path):
            print(f"Error: File {file_path} not found.")
            return []
            
        with open(file_path, 'r') as f:
            # Read lines and strip whitespace
            proceeding_ids = [line.strip() for line in f if line.strip()]
            
        print(f"Loaded {len(proceeding_ids)} proceeding IDs from {file_path}")
        return proceeding_ids
    except Exception as e:
        print(f"Error loading proceeding IDs from file: {e}")
        return []

def parse_tabs_from_proceeding(session_apex, proceeding_id):

    #base url
    detail_url = "https://apps.cpuc.ca.gov/apex/f"
    # this is the second half of url that directs to specific proceeding
    params = {
        "p": f"401:56::::RP,57,RIR:P5_PROCEEDING_SELECT:{proceeding_id}"
    }
    print(f"\n\nPROCEEDING   ::   {proceeding_id}\n\n")
    print(f"{detail_url}?p=401:56::::RP,57,RIR:P5_PROCEEDING_SELECT:{proceeding_id}")
    try:
        resp = session_apex.get(detail_url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"error : {proceeding_id} (status={resp.status_code})")
            return {}, None
    except requests.exceptions.RequestException as e:
        print(f"error: {e}")
        return {}, None

    soup = BeautifulSoup(resp.text, "html.parser")

    # fine tune llater
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

    # Look for data in the page
    if not any(value for key, value in proceeding_metadata.items() if key != 'proceeding_number'):
        # Try to find the proceeding title and description
        title_element = soup.find('span', {'id': 'P56_PROCEEDING_TITLE_DISPLAY'})
        if title_element:
            title_text = title_element.get_text(strip=True)
            if " - " in title_text:
                parts = title_text.split(" - ", 1)
                if len(parts) == 2:
                    proceeding_metadata['description'] = parts[1]

        # Try to find other metadata in the page text
        page_text = soup.get_text()

        # Filed By
        filed_by_match = re.search(r'Filed By:\s*([^\n]+)', page_text)
        if filed_by_match:
            filed_by_text = filed_by_match.group(1).strip()
            # Remove any other embedded metadata from filed_by
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


        print("[DEBUG] Extracted metadata:")
        for key, value in proceeding_metadata.items():
            print(f"  {key}: {value}")


    # The /ul tabs appear under <div class="sHorizontalTabsInner"><ul>
    tabs_ul = soup.select_one("div.sHorizontalTabsInner ul")
    if not tabs_ul:
        print(f"['sHorizontalTabsInner' not there for {proceeding_id}")
        return {}, proceeding_metadata

    tab_links = {}
    for li in tabs_ul.find_all("li"):
        a_tag = li.find("a")
        if a_tag:
            title = a_tag.get_text(strip=True)
            href = a_tag.get("href")
            # Convert relative f?p=401:57... to absolute
            full_url = urljoin("https://apps.cpuc.ca.gov/apex/", href)
            tab_links[title] = full_url

    print("successfully extracted proceeding metadata and tab links")
    return tab_links, proceeding_metadata


def extract_document_links_from_tab(session_apex, doc_tab_url, tab_name):
    print(f"extracting doc links from: {doc_tab_url} (Tab: {tab_name})")
    try:
        resp = session_apex.get(doc_tab_url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"could not retrieve the tab page: {doc_tab_url} (status={resp.status_code})")
            return [], []
    except requests.exceptions.RequestException as e:
        print(f"error - {e}")
        return [], []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Check for interactive report table
    table = soup.select_one("table.a-IRR-table")
    if not table:
        no_data_div = soup.select_one("div.a-IRR-noDataMsg")
        if no_data_div:
            msg = no_data_div.get_text(strip=True)
            print(f"no div - {msg}")
        else:
            print(f"no interactive report table found for tab {tab_name}")
        return [], []

    rows = table.select("tr")[1:]
    doc_links = []
    doc_metadata_list = []

    for row in rows:
        cells = row.select("td.u-tL")
        #metadata fields for this document
        doc_metadata = {
            'filing_date': '',
            'document_type': '',
            'filed_by': '',
            'description': '',
            'doc_link': ''
        }
        
        # Handle different tab types differently
        if tab_name == "Documents" and len(cells) >= 4:
            # Documents tab: Filing Date | Document Type | Filed By | Description
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
            # Rulings tab: Date | Ruling | Issued By | Description (if available)
            if cells[0]:
                doc_metadata['filing_date'] = clean_field_value(cells[0].get_text(strip=True))
            
            if cells[1]:
                # Set document type fixed for rulings
                doc_metadata['document_type'] = "RULING"
                
                # Add ruling description from text
                ruling_text = cells[1].get_text(strip=True)
                doc_metadata['description'] = clean_field_value(ruling_text)
                
                # Get the link
                link_tag = cells[1].find("a")
                if link_tag and link_tag.get("href", ""):
                    doc_link = link_tag["href"]
                    if doc_link.startswith("http://"):
                        doc_link = doc_link.replace("http://", "https://")
                    doc_links.append(doc_link)
                    doc_metadata['doc_link'] = doc_link
            
            if len(cells) >= 3 and cells[2]:
                doc_metadata['filed_by'] = clean_field_value(cells[2].get_text(strip=True))
            
            # If there's additional description in column 4
            if len(cells) >= 4 and cells[3]:
                additional_desc = clean_field_value(cells[3].get_text(strip=True))
                if additional_desc:
                    if doc_metadata['description']:
                        doc_metadata['description'] += " - " + additional_desc
                    else:
                        doc_metadata['description'] = additional_desc
                
        elif tab_name == "Decisions" and len(cells) >= 5:
            # Decisions tab: Adopted/Filed Date | Effective Date | Issued Date | Document Type | Description
            # The column structure is: 
            # 0: Adopted/Filed Date, 1: Effective Date, 2: Issued Date, 3: Document Type, 4: Description
            
            # Get dates
            if cells[0]:  # Adopted/Filed Date
                doc_metadata['filing_date'] = clean_field_value(cells[0].get_text(strip=True))
                doc_metadata['adopted_filed_date'] = doc_metadata['filing_date']  # Store this separately
            
            if cells[1]:  # Effective Date
                doc_metadata['effective_date'] = clean_field_value(cells[1].get_text(strip=True))
                
            if cells[2]:  # Issued Date
                doc_metadata['issued_date'] = clean_field_value(cells[2].get_text(strip=True))
            
            # Get document type and link
            if cells[3]:  # Document Type - may contain link
                doc_metadata['document_type'] = "DECISION"  # Fixed type for consistency
                
                # Check if there's a link in the document type field
                link_tag = cells[3].find("a")
                if link_tag and link_tag.get("href", ""):
                    doc_link = link_tag["href"]
                    if doc_link.startswith("http://"):
                        doc_link = doc_link.replace("http://", "https://")
                    doc_links.append(doc_link)
                    doc_metadata['doc_link'] = doc_link
                    
                    # Also store the displayed text with the link
                    link_text = link_tag.get_text(strip=True)
                    if link_text:
                        doc_metadata['document_type_text'] = clean_field_value(link_text)
                else:
                    # If no link, just get the text
                    doc_type_text = cells[3].get_text(strip=True)
                    if doc_type_text:
                        doc_metadata['document_type_text'] = clean_field_value(doc_type_text)
            
            # Get description
            if cells[4]:  # Description field
                doc_metadata['description'] = clean_field_value(cells[4].get_text(strip=True))
                
            # Filed by is CPUC for decisions
            doc_metadata['filed_by'] = "CPUC"
                
        # Handle the case where Decisions tab might only have 4 columns instead of 5
        elif tab_name == "Decisions" and len(cells) >= 4:
            # Reduced structure: Adopted/Filed Date | Effective Date | Document Type | Description
            if cells[0]:  # Adopted/Filed Date
                doc_metadata['filing_date'] = clean_field_value(cells[0].get_text(strip=True))
                doc_metadata['adopted_filed_date'] = doc_metadata['filing_date']
            
            if cells[1]:  # Effective Date
                doc_metadata['effective_date'] = clean_field_value(cells[1].get_text(strip=True))
            
            # Document Type with link (now at index 2)
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
            
            # Description (now at index 3)
            if cells[3]:
                doc_metadata['description'] = clean_field_value(cells[3].get_text(strip=True))
                
            doc_metadata['filed_by'] = "CPUC"
                
        elif tab_name == "Public Comments" and len(cells) >= 3:
            # Public Comments tab: Date | Comment | Commenter | Description (if available)
            if cells[0]:
                doc_metadata['filing_date'] = clean_field_value(cells[0].get_text(strip=True))
            
            if cells[1]:
                doc_metadata['document_type'] = "PUBLIC COMMENT"
                
                comment_text = cells[1].get_text(strip=True)
                doc_metadata['description'] = clean_field_value(comment_text)
                
                # Get the link
                link_tag = cells[1].find("a")
                if link_tag and link_tag.get("href", ""):
                    doc_link = link_tag["href"]
                    if doc_link.startswith("http://"):
                        doc_link = doc_link.replace("http://", "https://")
                    doc_links.append(doc_link)
                    doc_metadata['doc_link'] = doc_link
            
            if cells[2]:
                doc_metadata['filed_by'] = clean_field_value(cells[2].get_text(strip=True))

        # add metadata if link exists
        if doc_metadata['doc_link']:
            doc_metadata_list.append(doc_metadata)

    print(f"[INFO] Found {len(doc_links)} links and {len(doc_metadata_list)} metadata entries in {tab_name} tab")
    return doc_links, doc_metadata_list


def clean_field_value(value):
    if not value or not isinstance(value, str):
        return value
    
    # List of headers to remove from values
    headers = [
        "Service Lists:", 
        "Industry:", 
        "Filing Date:", 
        "Category:", 
        "Current Status:", 
        "Description:", 
        "Staff:"
    ]
    
    cleaned_value = value
    for header in headers:
        if header in cleaned_value:
            parts = cleaned_value.split(header)
            if len(parts) > 1:
                if parts[0].strip():
                    cleaned_value = parts[0].strip()
                # If there's nothing before the header, take what's after it
                # but only up to the next header if there is one
                else:
                    next_part = parts[1]
                    for h in headers:
                        if h in next_part:
                            next_part = next_part.split(h)[0].strip()
                            break
                    cleaned_value = next_part.strip()
    
    return cleaned_value


def collect_pdf_links(doc_link):
    session_docs = requests.Session()  # new session for external domain
    session_docs.headers.update({"User-Agent": USER_AGENT})

    print(f"collecting document links from {doc_link}")

    try:
        resp = session_docs.get(doc_link, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"error retrieving doc page at {doc_link} (status={resp.status_code})")
            return []
    except requests.exceptions.RequestException as e:
        print(f"error - request to {doc_link} failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Look for all document links, not just PDFs
    doc_urls = []

    # Also need to save metadata from this page - title, doc type, doc links (already handled), publish date
    # Look for links in the main content area
    content_area = soup.select_one("div#divDocContent")
    if content_area:
        for a_tag in content_area.find_all("a"):
            href = a_tag.get("href", "").strip()
            if href and not href.startswith("#") and not href.startswith("javascript:"):
                # Convert HTTP to HTTPS in all URLs
                if href.startswith("http://"):
                    href = href.replace("http://", "https://")
                full_url = urljoin(doc_link, href)
                doc_urls.append((full_url, a_tag.get_text(strip=True) or "Unnamed Document"))
    else:
        # If we can't find the specific content area - look for all links
        for a_tag in soup.find_all("a"):
            href = a_tag.get("href", "").strip()
            # Look for PDF links or PublishedDoc links which are common in CPUC site
            if (href.lower().endswith(".pdf") or
                "PublishedDocs" in href or
                "SearchRes.aspx" in href):
                # Convert HTTP to HTTPS in all URLs
                if href.startswith("http://"):
                    href = href.replace("http://", "https://")
                full_url = urljoin(doc_link, href)
                doc_urls.append((full_url, a_tag.get_text(strip=True) or "Unnamed Document"))

    print(f"found {len(doc_urls)} document links")
    return doc_urls


def save_links_to_file(proceeding_id, tab_name, links):
    os.makedirs("proceeding_links", exist_ok=True)
    os.makedirs(f"proceeding_links/{proceeding_id}", exist_ok=True)

    filename = f"proceeding_links/{proceeding_id}/{tab_name}.txt"

    with open(filename, "w") as f:
        f.write(f"{proceeding_id}\n")

        for i, (url, name) in enumerate(links):
            f.write(f"{url}\n")

    print(f"saved {len(links)} links to {filename}")


def main():
    session_apex = get_apex_session()
    if not session_apex:
        print("failed to initialize session")
        return

    ###########################################################################################################################
    ###########################################################################################################################
    # Load the proceeding IDs from proceeding_ids.txt file
    proceeding_ids = load_proceeding_ids_from_file()
    
    # If file reading fails or file is empty, use a limited sample set
    if not proceeding_ids:
        print("Warning: No proceeding IDs found in file. Using a small sample set instead.")
        proceeding_ids = ["A2502016"]
    ###########################################################################################################################
    ###########################################################################################################################

    # Process each proceeding
    for proc_id in proceeding_ids:
        print(f"\n\nProcessing proceeding: {proc_id}\n")

        tabs_data, proceeding_metadata = parse_tabs_from_proceeding(session_apex, proc_id)

        if proceeding_metadata:
            print("[INFO] Extracted proceeding metadata:")
            for key, value in proceeding_metadata.items():
                if value:
                    print(f"  {key}: {value}")

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
                print(f"[WARN] No '{tab_name}' tab found for {proc_id}")
                continue

            print(f"\n  {proc_id}  -  {tab_name} ")

            # Extract document links from the tab -  passing the tab name
            doc_links, doc_metadata_list = extract_document_links_from_tab(session_apex, tab_url, tab_name)

            if not doc_links:
                print(f"[WARN] No document links found in {tab_name} tab for {proc_id}")
                continue

            print(f"[INFO] Found {len(doc_links)} document links in {tab_name} tab")

            # Process document metadata
            if doc_metadata_list:
                print(f"[INFO] Found {len(doc_metadata_list)} document metadata entries in {tab_name} tab")
                for metadata in doc_metadata_list:
                    metadata['proceeding_id'] = proc_id
                    metadata['tab_name'] = tab_name
                    tab_metadata[tab_name].append(metadata)

            all_document_links = []
            for doc_link in doc_links:
                try:
                    document_links = collect_pdf_links(doc_link)

                    if not document_links:
                        print(f"[WARN] No documents found at {doc_link}")
                        continue

                    all_document_links.extend(document_links)

                    # Extract metadata for any documents not already processed
                    if not any(meta.get('doc_link') == doc_link for meta in doc_metadata_list):
                        for doc_url, doc_name in document_links:
                            # Set document type based on tab name
                            if tab_name == "Rulings":
                                doc_type = "RULING"
                            elif tab_name == "Decisions":
                                doc_type = "DECISION"
                            elif tab_name == "Public Comments":
                                doc_type = "PUBLIC COMMENT"
                            else:
                                doc_type = tab_name.rstrip('s').upper()
                                
                            document_metadata = {
                                'proceeding_id': proc_id,
                                'tab_name': tab_name,
                                'document_type': doc_type,
                                'filing_date': '',
                                'filed_by': '',
                                'description': doc_name,
                                'doc_link': doc_link,
                                'pdf_url': doc_url
                            }

                            # Try to extract filing date from the document name
                            date_patterns = [
                                r'(\d{1,2}/\d{1,2}/\d{2,4})',  # MM/DD/YYYY
                                r'(\d{1,2}-\d{1,2}-\d{2,4})',  # MM-DD-YYYY
                                r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}'
                                # Month DD, YYYY
                            ]

                            for pattern in date_patterns:
                                match = re.search(pattern, doc_name)
                                if match:
                                    document_metadata['filing_date'] = match.group(0)
                                    break

                            tab_metadata[tab_name].append(document_metadata)

                    time.sleep(.33)  # Remove later if too slow

                except Exception as e:
                    print(f"[ERROR] Error processing document link {doc_link}: {e}")
                    continue

            if all_document_links:
                save_links_to_file(proc_id, tab_name, all_document_links)
            else:
                print(f"[WARN] No documents found in {tab_name} tab for {proc_id}")

        # Save all metadata to CSV
        if proceeding_metadata:
            # Create a directory for the metadata
            os.makedirs(f"metadata/{proc_id}", exist_ok=True)

            # Save proceeding metadata
            proceeding_file = f"metadata/{proc_id}/proceeding.csv"
            with open(proceeding_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=proceeding_metadata.keys())
                writer.writeheader()
                writer.writerow(proceeding_metadata)
            print(f"[INFO] Saved proceeding metadata to {proceeding_file}")

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
                        print(f"exception {e}")
                print(f"[INFO] Saved {len(metadata_list)} {tab_name} metadata entries to {metadata_file}")


if __name__ == "__main__":
    main() 