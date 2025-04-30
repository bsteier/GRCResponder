import os
from pathlib import Path
from langchain_google_genai import ChatGoogleGenerativeAI
import json

DEFAULT_API_KEY_PATH = Path("gemini-key")
def set_api_key_from_path(api_key_path = DEFAULT_API_KEY_PATH):
    assert (api_key_path.is_file())
    # Path to your key file (can be relative or absolute)
    key_path = api_key_path

    # Read the API key from the file
    api_key = key_path.read_text().strip()
    set_api_key(api_key)

def set_api_key(api_key):
    if "GOOGLE_API_KEY" not in os.environ:
        os.environ["GOOGLE_API_KEY"] = api_key

def initialize_evaluation_llm(gemini_model = 'gemini-2.0-flash'):
    llm = ChatGoogleGenerativeAI(model=gemini_model)
    return llm

def load_model_output(path: Path) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def build_evaluation_prompt(model_output_text: str) -> str:
    prompt = f"""
    You are evaluating a retrieval-augmented generation (RAG) system. For each Q/A pair in the data below, you will:
    1. Assign a relevance score (0–5) based on how well the retrieved context matches the question.
       - 0: No relevance, the context is completely off.
       - 1: Very low relevance, context is weakly related.
       - 2: Some relevance, context contains some useful details, but is not fully aligned.
       - 3: Good relevance, context provides useful information that mostly answers the question.
       - 4: Very good relevance, context almost entirely answers the question, with minimal extra information.
       - 5: Perfect relevance, context directly and completely answers the question.

    2. Assign a usage score (0–5) based on whether the context was properly used in generating the answer:
       - 0: The context was not used at all.
       - 1: The context was partially used but not enough to affect the response.
       - 2: The context was mentioned but not effectively incorporated.
       - 3: The context was used, but there were gaps in how it was integrated.
       - 4: The context was effectively used, though some information might be missing.
       - 5: The context was fully integrated and used to generate the response.

    3. Optional: Identify and flag any hallucinations or unsupported claims. If the AI refers to information not found in the context, it should be noted.

    Please format the output as a JSON array with the following fields: "question", "relevance_score", "usage_score", "hallucination_notes".

    Here is the data to evaluate:
    {model_output_text}
    """
    return prompt


def evaluate_responses(responses: list, llm) -> list:
    all_metrics = []

    for output_text in responses:
        prompt = build_evaluation_prompt(output_text)
        response = llm.invoke(prompt)

        try:
            cleaned = str(response.content).strip().strip("`").replace("```json", "").replace("```", "").strip(
                "\\n").strip("json")
            metrics = json.loads(cleaned)
            all_metrics.extend(metrics)
        except json.JSONDecodeError:
            print("Failed to parse response as JSON. Here's the raw content:")
            print(response)

    return all_metrics

def evaluate_model_outputs_from_paths(paths: list, llm) -> list:
    responses = [load_model_output(Path(p)) for p in paths]
    return evaluate_responses(responses, llm)

