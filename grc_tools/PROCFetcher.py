from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import os
import re
import time
import html

TIMEOUT = 300

class PROCFetcher:
    DOMAIN_PATH = 'https://apps.cpuc.ca.gov/apex/'
    SEARCH_PAGE = 'f?p=401:5::::RP,5,RIR,57,RIR::'
    
    def __init__(self, polite=True):
        self._polite = polite
        self.session = None
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

    def saveProceedings(self, filename, verbose=False) -> list:
        self.startSession()

        if self.session is None:
            print('Session Failed To Start')
            return
        
        with sync_playwright() as playwright:
            chromium = playwright.chromium
            # launch browser, set headless to FALSE to see actual instance
            browser = chromium.launch(headless=True)
            page_context = browser.new_context()
            page = page_context.new_page()

            # go to CPUC main website
            try:
                page.goto(self.DOMAIN_PATH + self.SEARCH_PAGE)
            except Exception as e:
                print('Failed To load page')
                return
            
            self.createJson(filename)
            while True:
                proceedings = []
                current_results = page.query_selector('.a-IRR-pagination-label')

                if not current_results:
                    break

                current_results_text = current_results.inner_text()
                if verbose:
                    if current_results_text:
                        print(f'Current Results: {current_results_text}')

                # get all the links for this page
                proceeding_ids = page.query_selector_all('.u-tL[headers="PROCEEDING_STATUS_DESC"]')
                proceeding_links = [self.DOMAIN_PATH + proceeding.query_selector('a').get_attribute("href") for proceeding in proceeding_ids]

                #iterate through each link and call function per proceeding

                for link in proceeding_links:
                    # wait to be polite
                    if self._polite:
                        page.wait_for_timeout(TIMEOUT)
                    try:
                        proceedings.append(self.retrieveProceeding(link))
                    except Exception as e:
                        print(f'Error, could not reach page {link} with error: {e}')
                        continue
                    
                    if verbose:
                        print(f'Fetched {link}')
                self.appendProcs(proceedings, filename)

                # test early exit to see if 
                next_button = page.query_selector('.a-IRR-button--pagination[title="Next"]')
                if not next_button:
                    break
                next_button.click()
                page.wait_for_function(f"document.querySelector('.a-IRR-pagination-label').innerText !== {repr(current_results_text)}")
            
            self.session.close()
            self.session = None
            page_context.close()
            browser.close()
            playwright.stop()
            return proceedings


    # This will return the metadata for a single proceeding given its ID, useful
    # to use while creating databases for testing to make the second ChromaDB w/
    # proceeding descriptions
    def fetchSingleProceeding(self, proceeding_id):
        if not self.session:
            self.startSession()
        formatted_string = ''.join(c for c in proceeding_id if c.isalnum())
        proceeding_link = f"{self.DOMAIN_PATH}f?p=401:5::::RP,5,RIR,57,RIR:::{formatted_string}"

        proceeding_info = self.retrieveProceeding(proceeding_link)
        
        return proceeding_info



    def retrieveProceeding(self, link):
        # use requests
        if not self.session:
            self.startSession()
        
        page = self.session.get(link)
        if page.status_code != 200:
            print(f"Error fetching {link}: {page.status_code}")
            raise Exception(f"Error fetching {link}: {page.status_code}")
        
        soup = BeautifulSoup(page.text, 'html.parser')
        # find the link to the document
        page_header = soup.find('h1')
        proceeding_id_elem = page_header.get_text().split(' ')[0]
        proceeding_id = str(proceeding_id_elem) if proceeding_id_elem else None

        service_lists = soup.find_all('span', id='P56_SERVICE_LISTS')
        service_list = []
        for service in service_lists:
            anchor = service.find('a')
            if not anchor:
                continue
            href = anchor.get('href')
            if href:
                service_list.append(str(href))
        
        industry = self.getDataText(soup, 'P56_INDUSTRY')
        filing_date = self.getDataText(soup, 'P56_FILING_DATE')
        status = self.getDataText(soup, 'P56_STATUS')
        category = self.getDataText(soup, 'P56_CATEGORY')
        description = self.getDataText(soup, 'P56_DESCRIPTION')

        #filed_by = self.getDataText(soup, 'P56_FILED_BY')

        filed_html = soup.find('span', id='P56_FILED_BY')
        filed_text = filed_html.decode_contents() if filed_html else None
        filed_text = html.unescape(filed_text) if filed_text else None
        filed_arr = re.split(r'<br\s*/?>', filed_text) if filed_text else None
        clean_filed = [str(member.replace('</br>', '').strip()) for member in filed_arr] if filed_arr else None

        # Find all the 'span' elements with id='P56_STAFF'
        staff_html = soup.find('span', id='P56_STAFF')
        
        staff_text = staff_html.decode_contents() if staff_html else None
        staff_arr = re.split(r'<br\s*/?>', staff_text) if staff_text else None
        clean_staff = [str(member.replace('</br>', '').strip()) for member in staff_arr] if staff_arr else None

        metadata = {
            'proceeding_id': proceeding_id,
            'filed_by': clean_filed,
            'service_list': service_list,
            'industry': industry,
            'filing_date': filing_date,
            'status': status,
            'category': category,
            'description': description,
            'staff': clean_staff
        }

        return metadata

    def getDataText(self, soup, id):
        html = soup.find('span', id=f'{id}')
        if not html:
            return None
        retVal = str(html.get_text())
        if retVal == '':
            return None
        return retVal
    
    def createJson(self, filename):
        file = filename + '.json'
        with open(file, 'w') as f:
            json.dump([], f, indent=4)

    def appendProcs(self, proceedings, filename):
        file = filename + '.json'
        if not os.path.exists(file):
            self.createJson(filename)
        with open(file, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
        data.extend(proceedings)
        with open(file, 'w') as f:
            json.dump(data, f, indent=4)
            

def addProceedings(proceeding_links, filename):
    fetcher = PROCFetcher()
    fetcher.startSession()
    proceedings = []
    for link in proceeding_links:
        # wait to be polite
        time.sleep(0.2)
        try:
            proceedings.append(fetcher.retrieveProceeding(link))
        except Exception as e:
            print(f'Error, could not reach page {link} with error: {e}')
            continue
        print(f'Fetched {link}')
        

    fetcher.appendProcs(proceedings, filename)



if __name__ == "__main__":
    fetcher = PROCFetcher()
    fetcher.saveProceedings(verbose=True,filename='proceedings')

