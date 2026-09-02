from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


PROJECT_DIR = Path(__file__).resolve().parents[1]
VECTOR_DIR = PROJECT_DIR / "rag" / "vector_store"

COLLECTION_NAME = "rescuecloud_knowledge"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:0.5b"


client = chromadb.PersistentClient(path=str(VECTOR_DIR))

collection = client.get_collection(
    name=COLLECTION_NAME,
    embedding_function=DefaultEmbeddingFunction(),
)


def retrieve_context(question: str) -> tuple[str, list[str]]:
    results = collection.query(
        query_texts=[question],
        n_results=3,
    )

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    context_parts = []
    sources = []

    for document, metadata in zip(documents, metadatas):
        source = metadata["source"]

        context_parts.append(
            f"Source: {source}\n{document}"
        )

        if source not in sources:
            sources.append(source)

    return "\n\n".join(context_parts), sources


def generate_answer(question: str, context: str) -> str:
    prompt = f"""
You are the RescueCloud project assistant.

Answer only using the supplied RescueCloud context.
Do not invent commands, results, services, or project features.
If the answer is not available in the context, say:
"I do not have that information in the RescueCloud knowledge base."

Keep the answer clear and concise.

Context:
{context}

Question:
{question}

Answer:
""".strip()

    payload = json.dumps(
        {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
            },
        }
    ).encode("utf-8")

    request = Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))

    except (HTTPError, URLError) as error:
        raise RuntimeError(
            f"Could not connect to Ollama: {error}"
        ) from error

    return result["response"].strip()


def main() -> None:
    question = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "How does RescueCloud verify a backup?"
    )

    context, sources = retrieve_context(question)
    answer = generate_answer(question, context)

    print(f"\nQuestion: {question}\n")
    print(f"Answer: {answer}\n")
    print("Sources:")

    for source in sources:
        print(f"- {source}")


if __name__ == "__main__":
    main()
