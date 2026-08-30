from pathlib import Path
import re

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


PROJECT_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = PROJECT_DIR / "rag" / "knowledge"
VECTOR_DIR = PROJECT_DIR / "rag" / "vector_store"

# Chunking configuration
CHUNK_SIZE: int = 120
CHUNK_OVERLAP: int = 20

COLLECTION_NAME = "rescuecloud_knowledge"


def split_into_chunks(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
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


# ---------------------------------------------------------------------------
# Re-indexing
# ---------------------------------------------------------------------------
# To re-index after adding new knowledge documents:
#   1. Delete rag/vector_store/ (ChromaDB will be rebuilt)
#   2. Re-run: python3 rag/build_vector_store.py
# Note: chroma.sqlite3 drifts in the working tree — always run
#   git checkout backend/rag/vector_store/chroma.sqlite3
# before committing to avoid staging the binary vector store.


# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------
# DefaultEmbeddingFunction uses a lightweight sentence-transformer model.
# For better semantic search quality, replace with:
#   from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction
# This requires a Gemini API key set as GOOGLE_API_KEY environment variable.


# ---------------------------------------------------------------------------
# Collection size guidance
# ---------------------------------------------------------------------------
# The RescueCloud knowledge base (rag/knowledge/*.md) should contain:
#   - System architecture documentation
#   - HIPAA compliance mappings
#   - PITR recovery procedures
#   - Common incident response playbooks
# Keep total knowledge base size < 10 MB for reasonable embedding performance.


# ---------------------------------------------------------------------------
# Search quality tips
# ---------------------------------------------------------------------------
# If the RAG assistant returns irrelevant results:
#   1. Reduce CHUNK_SIZE to create more specific chunks
#   2. Increase TOP_K_CHUNKS in ask_rescuecloud.py
#   3. Improve document structure — use headings and bullet points
#   4. Add more targeted knowledge documents to rag/knowledge/
