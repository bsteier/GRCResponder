# This python file will be used to download the pdfs directly from the CPUC website, first it will retrieve the proceeding links
# then it will add a directory for if one does not exist for the proceeding

import os
import json
import requests
from CPUCFetcher import CPUCFetcher
import time

SAVE_DIR = 'D:\\CPUCDocuments'

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
        if 'proceeding_id' in item and 'filing_date' in item and len(item['filing_date']) >= 4 and int(item['filing_date'][-4::]) >= 2020:
            proceedings.append(item['proceeding_id'])
    
    return proceedings

def main():
    proceedings = getProceedings('companyFilter/proceedings.json')

    proceedings = [proceeding for proceeding in proceedings if proceeding not in os.listdir(SAVE_DIR)]
    
    for proceeding in proceedings:
        download_proceeding(proceeding)


if __name__ == "__main__":
    # Example usage
    main()