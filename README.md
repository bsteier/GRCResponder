# GRCResponder
## Project Overview
This project utilizes llama3.2 and RAG to deliver a working GRC Response assistant that lets users easily search and manage large quantities of written documents. It's going to include features like semantic search, AI driven response drafting, and a user interface that will streamline information retrieval, optimizing the working process. This system will have version tracking, document categorization, and file previewing. From a technical perspective, our solution will ideally have a search response time of less than 2 seconds, generate responses within 5 seconds, and process documents with 95% accuracy. 

## Scope
## Installation and Setup
Follow these steps to run the code:
1. Navigate to the `client` directory
2. Run `npm install`.
3. Navigate to the `server` directory.
4. Run `pip install`.
5. Run `uvicorn main:app --reload`.

## Setting up local database
1. Navigate to `server` directory.
2. Run `python models.py`.

## Setting up Document Vector Database

The Vector Database setup is split into three parts:

1. Proceeding Scraper: This involves downloading all proceeding metadata from the CPUC website and storing it in a JSON file.
2. Document Downloader: This script downloads all the documents associated with the proceedings and stores them in a specified directory.
3. Vector Database Builder: This script processes the directory that contains the downloaded documents and builds a vector database using all the documents.

To complete the first two steps, follow the instructions in the `grc_tools/README.md` file.

### Vector Database Setup

Once the documents are downloaded, you will want to build the vector database directly using the `multithreaded_insert.py` script in the `qdrant_utils` directory. This script will process the downloaded documents and insert them into the Qdrant vector database. Prior to running the script, you need to install the required dependencies by running the following command in the `qdrant_utils` directory:

```pip install -r requirements.txt```

You will need to replace the `LOCAL_PATH` global variable defined at the top of the `multithreaded_insert.py` file with the location of the directory that stores all the proceeding documents. Also, ensure the the `QDRANT_URL` and `COLLECTION_NAME` environment variables are set in the `.env` file, pointing to your Qdrant instance and desired collection name. Then, run the script from the `qdrant_utils` directory using:

```python multithreaded_insert.py```

### Notes

A Qdrant database must be running and setup prior to running the `multithreaded_insert.py` script. You can run and instance of Qdrant on a Docker container, or use a cloud instance to support scalability and easier management. Information on setting up a Qdrant instance can be found at the following links:

 Cloud Setup: [https://qdrant.tech/cloud/](https://qdrant.tech/cloud/) 

 Local Setup: [https://qdrant.tech/documentation/guides/installation/](https://qdrant.tech/documentation/guides/installation/).


The document scraping process will likely be the longest part of the setup and will require a decent amount of time and resources. For reference, there were about 50 GB of documents from proceedings filed from January 2020 to April 2025, which took about 24 hours to download and save due to wait times between requests sent to the website.

Lastly, the embedding process is a computationally expensive process, so it is recommended to use a GPU that supports CUDA to speed up the process. For reference, the script took about 8 hours running on 50 GB of documents on an A100 VM instance.

