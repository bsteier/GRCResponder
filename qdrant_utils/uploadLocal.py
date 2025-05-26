import json
import os
from qdrant_utils import create_embeddings_from_pdf, create_qdrant_points, upload_to_qdrant
import uuid

# Location of local directory
LOCAL_PATH = 'D:\\CPUCDocuments'

# function will take in directory and upload them to qdrant
def upload_documents(proceeding_directory: str):
    proceeding_directory = os.path.join(LOCAL_PATH, proceeding_directory)
    if not os.path.exists(proceeding_directory):
        print(f"Directory {proceeding_directory} does not exist.")
        return
    
    metadata_file = os.path.join(proceeding_directory, 'metadata.json')
    if not os.path.exists(metadata_file):
        print(f"Metadata file {metadata_file} does not exist.")
        return
    
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)

    # store embeddings locally, once we have enough points, we will upload them all to qdrant
    points = []

    # iterate through each document in metadata and retrieve the embeddings
    for doc in metadata:
        pdf_path = os.path.join(proceeding_directory, doc['document_id'] + '.pdf')

        if not os.path.exists(pdf_path):
            print(f"PDF file {pdf_path} does not exist.")
            continue
        
        with open(pdf_path, 'rb') as f:
            pdf_text = f.read()
        
        embeddings = create_embeddings_from_pdf(pdf_text, embedding_args={'chunk_size': 1024, 'chunk_overlap': 50})

        ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc['document_id']}_{i}"))for i in range(len(embeddings))]
    
        embedding_vals = [embedding['embedding'] for embedding in embeddings]
        payloads = [
            {
                'chunk_index': embedding['chunk_index'],
                'document_id': doc['document_id'],
                'proceeding_id': doc['proceeding_id'],
                'source_url': doc['source_url'],
                'text': embedding['text']
            }
            for embedding in embeddings
        ]

        newPoints = create_qdrant_points(ids, embedding_vals, payloads)
        if not newPoints:
            print(f"No points created for {doc['source_url']}.")
            continue
        
        points.extend(newPoints)
        print(f"Created {len(newPoints)} points for {doc['source_url']}")
        if len(points) > 200:
            upload_to_qdrant(points)
            points = []
    
    if len(points) > 0:
        upload_to_qdrant(points)
    
if __name__ == "__main__":
    # Example usage
    proceedings = ['A2106021', 'A2204016']
    for proceeding in proceedings:
        upload_documents(proceeding)
        print(f"Uploaded documents for {proceeding}.")