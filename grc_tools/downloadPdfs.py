# This python file will be used to download the pdfs directly from the CPUC website, first it will retrieve the proceeding links
# then it will add a directory for if one does not exist for the proceeding

import os
import json
import requests
from CPUCFetcher import CPUCFetcher
from PROCFetcher import PROCFetcher
import time

# This is the directory where all the proceedings along w/ their documents will be saved
SAVE_DIR = 'D:\\TestGRC\\Proceedings'
# This is the file that the proceedings will be saved to
PROCEEDING_FILE = 'D:\\TestGRC\\proceedings.json'

def download_pdf(link, pdf_name, save_path):
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    
    try:
        response = requests.get(link)
        response.raise_for_status() 
    except requests.RequestException as e:
        print(f"Failed to download {link}: {e}")
        return

    with open(os.path.join(save_path, pdf_name), 'wb') as pdf_file:
        pdf_file.write(response.content)
    print(f"Downloaded {pdf_name} to {save_path}")


def save_metadata(metadata, save_path):
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    
    save_metadata_path = os.path.join(save_path, 'metadata.json')
    with open(save_metadata_path, 'w') as metadata_file:
        json.dump(metadata, metadata_file, indent=4)
    print(f"Saved metadata to {save_metadata_path}")

def download_proceeding(proceeding_num, save_dir=SAVE_DIR):
    fetcher = CPUCFetcher(proceeding_num)
    
    try:
        proceeding_documents = fetcher.fetch_application_metadata(proceeding_num)
    except Exception as e:
        print(f"Failed to fetch proceeding data for {proceeding_num}: {e}")
        return

    # we have all the proceeding document metadata
    cleaned_proceedings = cleanProceedings(proceeding_documents)
    save_path = os.path.join(save_dir, proceeding_num)

    for doc in cleaned_proceedings:
        download_pdf(doc['source_url'], doc['document_id'] + '.pdf', save_path)
        time.sleep(1)
    
    save_metadata_path = os.path.join(save_path, 'metadata.json')
    with open(save_metadata_path, 'w') as metadata_file:
        json.dump(cleaned_proceedings, metadata_file, indent=4)


def cleanProceedings(proceeding_documents):
    return [doc for doc in proceeding_documents if '(Certificate Of Service)' not in doc["title"]]

def getProceedings(json_file: str):
    with open(json_file, 'r') as file:
        data = json.load(file)
    
    proceedings = []

    for item in data:
        if 'proceeding_id' in item and proceedingFilter(item['proceeding_id']):
            proceedings.append(item['proceeding_id'])
    
    return proceedings


def proceedingFilter(proceeding) -> bool:
    # this function is used to filter certain proceedings out in case a subset of the documents are being downloaded
    return True # default behavior is to not filer out any proceedings
    if 'filing_date' in proceeding:
        return dateFilter(proceeding['filing_date'], 2020, 2025)
    
def dateFilter(proceeding_date: str, year_low: int, year_high: int) -> bool:
    return len(proceeding_date) >= 4 and int(proceeding_date[-4::]) >= year_low and int(proceeding_date[-4::]) <= year_high


def main():

    # fetcher = PROCFetcher()
    # fetcher.saveProceedings(verbose=True,filename=PROCEEDING_FILE)

    proceedings = getProceedings(PROCEEDING_FILE)

    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

    proceedings = [proceeding for proceeding in proceedings if proceeding not in os.listdir(SAVE_DIR)]
    
    for proceeding in proceedings:
        download_proceeding(proceeding)



if __name__ == "__main__":
    # Example usage
    main()