import psycopg2
import requests
import os
from dotenv import load_dotenv
import sys

load_dotenv()
CHROMA = os.getenv("CHROMA_HOST")
POSTGRESQL = os.getenv("POSTGRESQL_URL")

# print(CHROMA)
# print(POSTGRESQL)
print(sys.executable)


try:
    # Check /health or any endpoint Chroma actually provides
    response = requests.get(f"{CHROMA}")
    print("\nCHROMA Server found")
except requests.exceptions.RequestException as e:
    print("Error connecting to ChromaDB:", e)


try:
    conn = psycopg2.connect(POSTGRESQL)
    print("Connected to the database successfully!")

    # Optionally, create a cursor and run a test query
    cursor = conn.cursor()
    cursor.execute("SELECT version();")  # Checking PostgreSQL version
    version = cursor.fetchone()
    print("PostgreSQL Version:", version)

    # Clean up
    cursor.close()
    conn.close()
except Exception as e:
    print("Error connecting to the database:", e)


exit()

