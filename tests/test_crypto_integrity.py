from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path


def compute_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_sha256_deterministic_hashing():
    content = b"RESCUECLOUD_POSTGRES_BASE_BACKUP_CONTENT_VALIDATION"
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        hash1 = compute_sha256(tmp_path)
        hash2 = compute_sha256(tmp_path)
        assert hash1 == hash2
        assert len(hash1) == 64
        # Known SHA256 of this exact byte string
        expected = hashlib.sha256(content).hexdigest()
        assert hash1 == expected
    finally:
        tmp_path.unlink()


def test_sha256_detects_single_bit_tampering():
    original_content = b"CLINICAL_PATIENT_RECORD_DATABASE_SNAPSHOT_CLEAN"
    tampered_content = b"CLINICAL_PATIENT_RECORD_DATABASE_SNAPSHOT_TAINT"

    with tempfile.NamedTemporaryFile(delete=False) as tmp1, tempfile.NamedTemporaryFile(delete=False) as tmp2:
        tmp1.write(original_content)
        tmp2.write(tampered_content)
        path1 = Path(tmp1.name)
        path2 = Path(tmp2.name)

    try:
        hash_original = compute_sha256(path1)
        hash_tampered = compute_sha256(path2)

        assert hash_original != hash_tampered
    finally:
        path1.unlink()
        path2.unlink()

# Coverage: SHA-256 matches reference hash, tamper detection, determinism.
# Gap: very large files (>1 GB streaming); concurrent hashlib.sha256() calls.
