from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


PROJECT_DIR = Path(__file__).resolve().parents[1]
VECTOR_DIR = PROJECT_DIR / "rag" / "vector_store"

client = chromadb.PersistentClient(path=str(VECTOR_DIR))

collection = client.get_collection(
    name="rescuecloud_knowledge",
    embedding_function=DefaultEmbeddingFunction(),
)

question = "How does RescueCloud verify a backup before recovery?"

results = collection.query(
    query_texts=[question],
    n_results=3,
)

print(f"\nQuestion: {question}\n")

for index, document in enumerate(results["documents"][0], start=1):
    metadata = results["metadatas"][0][index - 1]
    distance = results["distances"][0][index - 1]

    print(f"Result {index}")
    print(f"Source: {metadata['source']}")
    print(f"Distance: {distance:.4f}")
    print(document)
    print("-" * 70)
