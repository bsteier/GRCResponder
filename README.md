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
