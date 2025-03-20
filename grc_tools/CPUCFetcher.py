from bs4 import BeautifulSoup, Tag
import requests
from io import StringIO
import csv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
## Class that will fetch the documents from the website


class CPUCFetcher:
    URL_BASE = 'https://apps.cpuc.ca.gov/apex/f?p=401:{page_num}::{doc_type}::RP,57,RIR:P5_PROCEEDING_SELECT:{proc_num}'

    PAGE_NUM = {
        'proceeding': '56',
        'documents': '57',
        'rulings': '58',
        'decisions': '59'
    }

    DOC_PREFIX = 'https://docs.cpuc.ca.gov'

    def __init__(self, polite=True):
        self.session = None
        self._polite = polite
        pass
    
    def startSession(self):
        if self.session is None:
            try:
                self.session = requests.Session()
            # set headers for session
                self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'})
                # allow for retries
                retry_strategy = Retry(
                total=3,
                status_forcelist=[500, 502, 503, 504],
                backoff_factor=1
                )
                adapter = HTTPAdapter(max_retries=retry_strategy)
                self.session.mount('http://', adapter)
                self.session.mount('https://', adapter)
            except Exception as e:
                print(f'Failed to start session:{e}')
                self.session = None

    def fetch_application(self, proceeding: str):
        documents = self.fetch_application_metadata(proceeding)
        return [document['source_url'] for document in documents]

    # Gets all of the document metadata for a given proceeding
    def fetch_application_metadata(self, proceeding: str):
        self.startSession()

        if not proceeding:
            raise ValueError('NONSPECIFIED PROCEEDING')
        
        # strip the '-. ' characters from the proceeding string
        formatted_string = ''.join(c for c in proceeding if c.isalnum())
        
        documents = []
        seen_urls = set()

        # iterate through different pages to find the url's
        for page_type in ['documents', 'rulings', 'decisions']:
            self._addDocs(formatted_string, page_type, documents, seen_urls)

        # close session    
        self.session.close()
        self.session = None

        return documents
            
    def _addDocs(self, proceeding: str, page_type: str, documents: list, seen_urls: set):
        page_num = self.PAGE_NUM[page_type]
        # Get url that will find the csv file to download and parse through
        url = self.URL_BASE.format(page_num=page_num, proc_num=proceeding, doc_type='CSV')
        
        # Fetch the page content
        try:
            response = self.session.get(url)
        except Exception as e:
            print(f"Failed to fetch {url} with exception: {e}")
            return
        
        if response.status_code != 200:
            print(f"Error fetching {url}: {response.status_code}")

        # successfully requested .csv file, iterate through and save metadata
        csv_file = StringIO(response.text)
        csv_reader = csv.reader(csv_file)
        headers = next(csv_reader)

        # If it is the documents or rulings page, the link is the 1 indexed column
        # If it is a decision, it is the 3rd indexed column
        href_index = 1 if page_type in ['documents', 'rulings'] else 3

        for row in csv_reader:
            # here, we want to process a CSV row that has all the important metadata
            # We need to modify the processDocument method to take in a row of the CSV
            # this will require going to the actual proceeding page and scraping the description

            html = BeautifulSoup(row[href_index], 'html.parser')
            # find the link to the document
            if not html.find('a'):
                print(f"No link found in row: {row}")
                continue
            
            doc_link = html.find('a')['href']

            # we need to skip over the documents that do not link to the pdfs
            if 'orderadocument' in doc_link:
                continue

            # For some reason, the .get pauses on the http: links
            # replace with https link to avoid this
            if doc_link.startswith('http:'):
                doc_link = doc_link.replace('http:', 'https:')
            
            # Even though not a pdf url, we still check to see if the url has been seen
            if doc_link in seen_urls:
                # print for debugging already seen documents

                # print(f"Document already seen: {doc_link}")
                continue
            seen_urls.add(doc_link)

            self._saveDocs(doc_link, documents, seen_urls)
    


    # iterates through the pdf documents page to get each document for processing
    def _saveDocs(self, doc_url: str, documents: list, seen_urls: set):
        # print statement for debugging
        #print(f"Fetching documents from: {doc_url}")

        try:
            # Add wait time to be polite to the server so we do not get in trouble
            if self._polite:
                time.sleep(1)
            response = self.session.get(doc_url,timeout=10)
        except requests.RequestException as e:
            print(f"Failed to fetch {doc_url} with exception: {e}")
            return
        
        if response.status_code != 200:
            print(f"Error fetching {doc_url}: {response.status_code}")
            return
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        doc_table = soup.find('table', class_='ResultTable')

        if not doc_table:
            print(f'No documents found: {doc_url}')
            return

        table_body = doc_table.find('tbody')

        if not table_body:
            print(f'No docs found: {doc_url}')
            return

        doc_rows = table_body.find_all('tr')
        
        for doc_row in doc_rows[::2]:
            self.processDocument(doc_row, documents, seen_urls)
        
        return
    

    # Takes in a <tr> html element w/ all relevant data for the document
    # and extracts the relevant metadata

    def processDocument(self, doc_row: Tag, documents: list, seen_urls: set):
        title_text = doc_row.find('td', class_='ResultTitleTD').get_text(separator='\n')

        if not title_text:
            print('could not find title text')
            return
        
        # parse the text into the Proceedings for this particular document
        # and the title of the document
        parsed_text = title_text.split('\n')
        title = parsed_text[0]
        proceedings = self._parseProceedings(parsed_text[1])
        
        doc_type = doc_row.find('td', class_='ResultTypeTD').text
        published_date = doc_row.find('td', class_='ResultDateTD').text

        # download the PDF
        pdf_link = self.DOC_PREFIX + doc_row.find('td', class_='ResultLinkTD').find('a')['href']

        # not sure if this is the best document_id, clarify
        document_id = pdf_link.split('/')[-1].split('.')[0]

        metadata = {
            'document_id': document_id,
            # THIS CURRENTLY ONLY STORES THE FIRST PROCEEDING THAT IT IS RELATED TO, THERE COULD BE 
            # MULTIPLE
            'proceeding_id': proceedings[0],
            'source_url': pdf_link,
            'published_date': published_date,
            'title': title,
            'doc_type': doc_type
        }

        
        # Check if the document has already been seen
        if metadata['source_url'] in seen_urls:
            # print statement for debugging
            # print(f"Document already seen: {metadata['source_url']}")
            return

        seen_urls.add(metadata['source_url'])
        documents.append(metadata)

    @staticmethod
    def _parseProceedings(proc_text: str):
        procs = proc_text.split('; ')
        procs[0] = procs[0].split(' ')[1]
        return procs    

if __name__ == "__main__":
    fetcher = CPUCFetcher()
    # Example usage
    proceeding = "A.21-06-021"
    documents = fetcher.fetch_application(proceeding)
    print(documents)
    