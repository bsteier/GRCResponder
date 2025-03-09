import os
import psycopg2
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from search_engine.view_embeddings import list_collections, cDB_client

# Load environment variables
load_dotenv()
CHROMA_HOST = os.getenv("CHROMA_HOST")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASS = os.getenv("POSTGRES_PASS")
EMBED_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"

def pg_connection():
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASS
    )
    return conn

def doc_chunks_table_exists(conn):

    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS doc_chunks (
                id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
                chunk_text TEXT,
                chunk_metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
    conn.commit()
    print("doc_chunks table exists")

def keyword_search(query, limit=5):

    print(f"Performing keyword search for: '{query}'")
    
    conn = pg_connection()
    results = []
    
    try:
        # Ensure the doc_chunks table exists
        doc_chunks_table_exists(conn)
        
        with conn.cursor() as cur:
            sql = """
                SELECT 
                    c.id, 
                    c.document_id, 
                    d.proceeding_id,
                    d.description as doc_title,
                    d.pdf_url,
                    c.chunk_text,
                    c.chunk_metadata,
                    ts_rank_cd(to_tsvector('english', c.chunk_text), plainto_tsquery('english', %s)) as rank
                FROM 
                    doc_chunks c
                JOIN 
                    documents d ON c.document_id = d.id
                WHERE 
                    to_tsvector('english', c.chunk_text) @@ plainto_tsquery('english', %s)
                ORDER BY 
                    rank DESC
                LIMIT %s
            """
            cur.execute(sql, (query, query, limit))
            chunk_results = cur.fetchall()
            
            # If no results in chunks, fall back to searching in the full document text
            if not chunk_results and limit > 0:
                print("o results found in chunks, searching in full documents")
                sql = """
                    SELECT 
                        d.id, 
                        d.id as document_id,
                        d.proceeding_id,
                        d.description as doc_title,
                        d.pdf_url,
                        d.doc_text as chunk_text,
                        '{}' as chunk_metadata,
                        ts_rank_cd(to_tsvector('english', d.doc_text), plainto_tsquery('english', %s)) as rank
                    FROM 
                        documents d
                    WHERE 
                        to_tsvector('english', d.doc_text) @@ plainto_tsquery('english', %s)
                    ORDER BY 
                        rank DESC
                    LIMIT %s
                """
                cur.execute(sql, (query, query, limit))
                chunk_results = cur.fetchall()
            
            for row in chunk_results:
                chunk_id, doc_id, proc_id, doc_title, pdf_url, chunk_text, chunk_metadata, rank = row
                
                # Format the result
                result = {
                    "chunk_id": chunk_id,
                    "document_id": doc_id,
                    "proceeding_id": proc_id,
                    "document_title": doc_title,
                    "source_url": pdf_url,
                    "chunk_text": chunk_text,
                    "chunk_metadata": chunk_metadata,
                    "rank": rank,
                    "search_type": "keyword"
                }
                results.append(result)
                
            print(f"Found {len(results)} results for keyword search")
    finally:
        conn.close()
        
    return results

def semantic_search(query, limit=5, collection_name = "invalde-collection-choice"):

    print(f"Performing semantic search for: '{query}'")
    
    #  the embedding model
    model = SentenceTransformer(EMBED_MODEL_NAME)
    
    client = cDB_client()
    collection = client.get_collection(name=collection_name)
    
    query_embedding = model.encode(query).tolist()
    chroma_results = collection.query(
        query_embeddings=[query_embedding],
        n_results=limit,
        include=["metadatas", "distances", "documents"]
    )
    
    results = []
    if len(chroma_results['ids'][0]) > 0:
        for i, (item_id, metadata, distance) in enumerate(zip(
            chroma_results['ids'][0], 
            chroma_results['metadatas'][0],
            chroma_results['distances'][0]
        )):
            # Convert distance to similarity score (1 - distance)
            similarity = 1 - distance
            
            result = {
                "chunk_id": metadata.get('chunk_index'),
                "document_id": metadata.get('document_id'),
                "proceeding_id": metadata.get('proceeding_id'),
                "source_url": metadata.get('source_url'),
                "chunk_text": metadata.get('text'),
                "similarity": similarity,
                "search_type": "semantic"
            }
            results.append(result)
            
    print(f"Found {len(results)} results for semantic search")
    return results

def hybrid_search(query, keyword_weight=0.3, semantic_weight=0.7, limit=5):
    # performss both keyword and semantic search and combine the results.

    print(f"Performing hybrid search for: '{query}'")
    keyword_results = keyword_search(query, limit=limit*2)
    semantic_results = semantic_search(query, limit=limit*2)
    
    combined_results = {}
    
    #keyword results
    for result in keyword_results:
        key = f"{result['document_id']}_{result['chunk_id']}"
        if key not in combined_results:
            combined_results[key] = result.copy()
            # rank on 0-1 scale (PostgreSQL ts_rank_cd returns values 0-1)
            combined_results[key]['combined_score'] = result['rank'] * keyword_weight
        
    #  semantic results
    for result in semantic_results:
        key = f"{result['document_id']}_{result['chunk_id']}"
        if key in combined_results:
            #result exists in both searches, combine the scores
            combined_results[key]['similarity'] = result['similarity']
            combined_results[key]['combined_score'] += result['similarity'] * semantic_weight
            combined_results[key]['search_type'] = "hybrid"
        else:
            # only in semantic results
            combined_results[key] = result.copy()
            combined_results[key]['combined_score'] = result['similarity'] * semantic_weight
    
    results_list = list(combined_results.values())
    results_list.sort(key=lambda x: x.get('combined_score', 0), reverse=True)
    
    results_list = results_list[:limit]
    
    print(f"Found {len(results_list)} results for hybrid search")
    return results_list

def show_results(results):
    if not results:
        print("No results found.")
        return
        
    print(f"\n{'='*80}")
    print(f"Found {len(results)} results:")
    print(f"{'='*80}")
    
    for i, result in enumerate(results):
        print(f"\nResult {i+1}:")
        
        if result.get('search_type') == 'keyword':
            print(f"  Relevance: {result.get('rank', 0):.4f} (Keyword Match)")
        elif result.get('search_type') == 'semantic':
            print(f"  Similarity: {result.get('similarity', 0):.4f} (Semantic Match)")
        else:  # hybrid
            print(f"  Combined Score: {result.get('combined_score', 0):.4f} (Hybrid Match)")
            if 'rank' in result:
                print(f"  Keyword Relevance: {result.get('rank', 0):.4f}")
            if 'similarity' in result:
                print(f"  Semantic Similarity: {result.get('similarity', 0):.4f}")
        
        print(f"  Document ID: {result.get('document_id')}")
        if 'document_title' in result:
            print(f"  Document Title: {result.get('document_title')}")
        
        # Show text preview (first 150 characters)
        text = result.get('chunk_text', '')
        text_preview = text[:150] + "..." if len(text) > 150 else text
        print(f"  Text: {text_preview}")
        print(f"  {'-'*70}")

def main():
    print("\nGRC Document Search")
    print("===================")
    print("1. Keyword Search")
    print("2. Semantic Search")
    print("3. Hybrid Search")
    print("4. view collections")

    
    choice = input("\nSelect search type (1-4) : ").strip() or "4"

    if(choice != "4"):
        collection = input("\ncollection name : ").strip()
        query = input("\nEnter your search query: ").strip()
        if not query:
            query = "regulatory requirements"  # Default query

        limit = input("\nMaximum number of results [5]: ").strip() or "5"
        limit = int(limit)


    if choice == "1":
        results = keyword_search(query, limit)
    elif choice == "2":
        results = semantic_search(query, limit, collection)
    elif choice == "3":
        # choose ratio
        keyword_weight = 0.3
        semantic_weight = 0.7
        results = hybrid_search(query, keyword_weight, semantic_weight, limit)
    else:
        client = cDB_client()
        list_collections(client)
        return
    
    show_results(results)

if __name__ == "__main__":
    main() 