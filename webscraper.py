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
            proceeding_metadata['filed_by'] = filed_by_match.group(1).strip()

        # Industry
        industry_match = re.search(r'Industry:\s*([^\n]+)', page_text)
        if industry_match:
            proceeding_metadata['industry'] = industry_match.group(1).strip()

        # Filing Date
        filing_date_match = re.search(r'Filing Date:\s*([^\n]+)', page_text)
        if filing_date_match:
            proceeding_metadata['filing_date'] = filing_date_match.group(1).strip()

        # Current Status
        status_match = re.search(r'Current Status:\s*([^\n]+)', page_text)
        if status_match:
            proceeding_metadata['current_status'] = status_match.group(1).strip()

        # Staff
        staff_match = re.search(r'Staff:\s*([^\n]+)', page_text)
        if staff_match:
            proceeding_metadata['staff'] = staff_match.group(1).strip()

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


def extract_document_links_from_tab(session_apex, doc_tab_url):

    print(f"extracting doc links from: {doc_tab_url}")
    try:
        resp = session_apex.get(doc_tab_url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print("could not retrieve the tab page:", doc_tab_url)
            return [], []
    except requests.exceptions.RequestException as e:
        print(f"error - {e}")
        return [], []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Check if the interactive report table is present
    table = soup.select_one("table.a-IRR-table")
    if not table:
        no_data_div = soup.select_one("div.a-IRR-noDataMsg")
        if no_data_div:
            msg = no_data_div.get_text(strip=True)
            print(f"no div - {msg}")
        else:
            print("no interactive report table found")
        return [], []

    # Each data row is after the header row
    rows = table.select("tr")[1:]
    doc_links = []
    doc_metadata_list = []

    for row in rows:
        cells = row.select("td.u-tL")
        #columns: Filing Date | Document Type | Filed By | Description
        
        # Initialize metadata for this document
        doc_metadata = {
            'filing_date': '',
            'document_type': '',
            'filed_by': '',
            'description': '',
            'doc_link': ''
        }
        
        # Extract metadata from cells
        if len(cells) >= 4:  # there are 5 colums expected - some will be blank??
            # Filing Date
            if cells[0]:
                doc_metadata['filing_date'] = cells[0].get_text(strip=True)
            
            # Document Type and Link
            doc_type_cell = cells[1]
            if doc_type_cell:
                doc_metadata['document_type'] = doc_type_cell.get_text(strip=True)
                link_tag = doc_type_cell.find("a")
                if link_tag and link_tag.get("href", "").startswith("http://docs.cpuc.ca.gov"):
                    doc_link = link_tag["href"]
                    doc_links.append(doc_link)
                    doc_metadata['doc_link'] = doc_link
            
            # filed By
            if cells[2]:
                doc_metadata['filed_by'] = cells[2].get_text(strip=True)
            
            # description
            if cells[3]:
                doc_metadata['description'] = cells[3].get_text(strip=True)

            # add metadata if link exists
            if doc_metadata['doc_link']:
                doc_metadata_list.append(doc_metadata)

    return doc_links, doc_metadata_list


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
        print(f"errror - request to {doc_link} failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Look for all document links, not just PDFs
    doc_urls = []


    #also need to save metadate from this page - title - doc type - doc links (already handled) - publish date(can be differrent for previous pages listing
    # Look for links in the main content area
    content_area = soup.select_one("div#divDocContent")
    if content_area:
        # Find all links in the content area
        for a_tag in content_area.find_all("a"):
            href = a_tag.get("href", "").strip()
            if href and not href.startswith("#") and not href.startswith("javascript:"):
                full_url = urljoin(doc_link, href)
                doc_urls.append((full_url, a_tag.get_text(strip=True) or "Unnamed Document"))
    else:
        # If we can't find the specific content area, look for all links
        for a_tag in soup.find_all("a"):
            href = a_tag.get("href", "").strip()
            # Look for PDF links or PublishedDoc links which are common in CPUC site
            if (href.lower().endswith(".pdf") or
                "PublishedDocs" in href or
                "SearchRes.aspx" in href):
                full_url = urljoin(doc_link, href)
                doc_urls.append((full_url, a_tag.get_text(strip=True) or "Unnamed Document"))

    print(f"found {len(doc_urls)} document links")
    return doc_urls

def save_links_to_file(proceeding_id, tab_name, links):

    os.makedirs("../webscaper/proceeding_links", exist_ok=True)
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
    # the proceeding IDs scrape
    proceeding_ids =["A2212008"] # ["A2502013", "A2502014", "A2502016", "A2502012", "A2502009"]  # Add more IDs as needed
    ###########################################################################################################################

    # process each proceeding
    for proc_id in proceeding_ids:

        # check the tabs for this proceeding and extract metadata
        tabs_data, proceeding_metadata = parse_tabs_from_proceeding(session_apex, proc_id)

        if proceeding_metadata:
            print("[INFO] Extracted proceeding metadata:")
            for key, value in proceeding_metadata.items():
                if value:
                    print(f"  {key}: {value}")

        # eval each tab
        tabs_to_process = {
            "Documents": tabs_data.get("Documents"),
            "Rulings": tabs_data.get("Rulings"),
            "Decisions": tabs_data.get("Decisions"),
            "Public Comments": tabs_data.get("Public Comments")
        }

        # all document metadata storred here
        all_document_metadata = []

        for tab_name, tab_url in tabs_to_process.items():
            if not tab_url:
                print(f"[WARN] No '{tab_name}' tab found for {proc_id}")
                continue

            print(f"\n  {proc_id}  -  {tab_name} ")

            # Extract document links from the tab
            doc_links, doc_metadata_list = extract_document_links_from_tab(session_apex, tab_url)

            if not doc_links:
                print(f"[WARN] No document links found in {tab_name} tab for {proc_id}")
                continue

            print(f"[INFO] Found {len(doc_links)} document links in {tab_name} tab")

            # Process each document link
            all_document_links = []

            if doc_metadata_list:
                print(f"[INFO] Found {len(doc_metadata_list)} document metadata entries in {tab_name} tab")
                for metadata in doc_metadata_list:
                    metadata['proceeding_id'] = proc_id
                    metadata['tab_name'] = tab_name
                    all_document_metadata.append(metadata)

            for doc_link in doc_links:
                try:
                    document_links = collect_pdf_links(doc_link)

                    if not document_links:
                        print(f"[WARN] No documents found at {doc_link}")
                        continue

                    all_document_links.extend(document_links)

                    # Extract metadata for each document
                    # Only process documents that don't already have metadata
                    if not any(meta.get('doc_link') == doc_link for meta in doc_metadata_list):
                        for doc_url, doc_name in document_links:
                            document_metadata = {
                                'proceeding_id': proc_id,
                                'tab_name': tab_name,
                                'doc_type': tab_name.rstrip('s').upper(),
                                'filing_date': '',
                                'filed_by': '',
                                'description': doc_name,
                                'pdf_url': doc_url,
                                'doc_link': doc_link
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
                                    document_metadata['filing_date'] = match.group(1)
                                    break

                            all_document_metadata.append(document_metadata)

                    time.sleep(1) #remove laterrr if too slow

                except Exception as e:
                    print(f"[ERROR] Error processing document link {doc_link}: {e}")
                    continue

            if all_document_links:
                save_links_to_file(proc_id, tab_name, all_document_links)
            else:
                print(f"[WARN] No documents found in {tab_name} tab for {proc_id}")

        # save all metadata to CSV
        if proceeding_metadata or all_document_metadata:
            # Create a directory for the metadata if it doesn't exist
            os.makedirs(f"metadata/{proc_id}", exist_ok=True)

            #proceeding metadata saved
            if proceeding_metadata:
                proceeding_file = f"metadata/{proc_id}/proceeding.csv"
                with open(proceeding_file, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=proceeding_metadata.keys())
                    writer.writeheader()
                    writer.writerow(proceeding_metadata)
                print(f"[INFO] Saved proceeding metadata to {proceeding_file}")

            #document metadata saved
            if all_document_metadata:
                document_file = f"metadata/{proc_id}/documents.csv"
                with open(document_file, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=all_document_metadata[0].keys())
                    writer.writeheader()
                    writer.writerows(all_document_metadata)
                print(f"[INFO] Saved {len(all_document_metadata)} document metadata entries to {document_file}")


if __name__ == "__main__":
    main()
