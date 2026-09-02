from pathlib import Path
import re

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


PROJECT_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = PROJECT_DIR / "rag" / "knowledge"
VECTOR_DIR = PROJECT_DIR / "rag" / "vector_store"

COLLECTION_NAME = "rescuecloud_knowledge"


def split_into_chunks(
    text: str,
    chunk_size: int = 120,
    overlap: int = 20,
) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    words = cleaned.split()

    chunks = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])

        if chunk:
            chunks.append(chunk)

        if end == len(words):
            break

        start = end - overlap

    return chunks


documents = []
metadatas = []
ids = []

for file_path in sorted(KNOWLEDGE_DIR.glob("*.md")):
    text = file_path.read_text(encoding="utf-8")
    chunks = split_into_chunks(text)

    for index, chunk in enumerate(chunks, start=1):
        documents.append(chunk)

        metadatas.append(
            {
                "source": file_path.name,
                "chunk_number": index,
            }
        )

        ids.append(f"{file_path.stem}_{index}")


VECTOR_DIR.mkdir(parents=True, exist_ok=True)

client = chromadb.PersistentClient(
    path=str(VECTOR_DIR)
)

try:
    client.delete_collection(COLLECTION_NAME)
except Exception:
    pass

collection = client.create_collection(
    name=COLLECTION_NAME,
    embedding_function=DefaultEmbeddingFunction(),
    metadata={"hnsw:space": "cosine"},
)

collection.add(
    ids=ids,
    documents=documents,
    metadatas=metadatas,
)

print(f"Vector database: {VECTOR_DIR}")
print(f"Documents indexed: {len(documents)}")
print(f"Collection count: {collection.count()}")
