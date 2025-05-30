from sentence_transformers import CrossEncoder, SentenceTransformer
from qdrant_client import QdrantClient
from langchain_google_genai import ChatGoogleGenerativeAI
import torch

# Initialize the sentenceTransformer and cross-encoder models used for embedding and scoring
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', device=device)

def query_db(query: str, qdrant_client: QdrantClient, collection_name: str, k: int=5):
    try:
        query_embedding = embedding_model.encode(query).tolist()

        response = qdrant_client.query_points(
            collection_name=collection_name,
            query=query_embedding,
            limit=k,
            with_payload=True
        )
    except Exception as e:
        print("hi", e)

    return response.points


# Number of samples to get before cross-encoder filtering
CROSS_ENCODER_SAMPLE = 30
def crossEncoderQuery(query: str, qdrant_client: QdrantClient, collection_name: str, k: int=5):
    # This will just return alot of points from the db prior to cross-encoder filtering
    print("in cross encoder")
    points = query_db(
        query=query, 
        qdrant_client=qdrant_client,
        collection_name=collection_name,
        k=CROSS_ENCODER_SAMPLE
    )

    scores = model.predict(
        [(query, point.payload['text']) for point in points],
        show_progress_bar=True
    )

    # we will sort the points by their cross-encoder score and return the top k
    points = sorted(zip(points, scores), key=lambda x: x[1], reverse=True)

    points = [point for point, _ in points[:k]]
    scores = [score for score in points[:k]] # we will not return scores for now, maybe for testing and weight manipulation
    
    print("complete")
    return points


# Function that creates a hypotetical passage to query the LLM
def hydeRetrieval(query: str, qdrant_client: QdrantClient, collection_name: str, llm: ChatGoogleGenerativeAI, k: int=5):
    new_query = generateHydePassage(query, llm)
    points = query_db(
        query=new_query, 
        qdrant_client=qdrant_client, 
        collection_name=collection_name, 
        k=k
    )
    return points


def hydeCrossEncoderRetrieval(query: str, llm: ChatGoogleGenerativeAI, qdrant_client: QdrantClient, collection_name: str, k: int=5):
    new_query = generateHydePassage(query, llm)
    points = crossEncoderQuery(
        query=new_query, 
        qdrant_client=qdrant_client,
        collection_name=collection_name,
        k=k
    )

    return points


# Function that generates a hypothetical passage to pass to LLM
def generateHydePassage(query: str, llm: ChatGoogleGenerativeAI):
    prompt = f"""
    Generate a hypothetical passage that could appear in a formal regulatory filing or decision document from a General Rate Case (GRC) proceeding. 

    The passage should address the following question or issue:

    "{query}"

    Write in a professional, regulatory tone, using language typical of official filings. The response should be 3–5 sentences long and present a plausible justification or explanation as a regulator might write.
    """
    new_query = llm.invoke(prompt)
    return new_query.content

def prettyPrintPoints(points):
    print(
        f"\n{'-'*100}\n".join(
            [f"Document {i+1}, Distance {point.score}:\n\n" + point.payload['text'] for i, point in enumerate(points)]
        )
    )

if __name__ == "__main__":


    # Example query
    query = "Explain PG&E's goal for their 2023 GRC"
    # Example cross-encoder query
    crossEncoderQuery(query)