"""Pytest configuration and test environment setup.

Ensures required environment variables are set before any tests import backend modules.
"""

from __future__ import annotations

import os

# Set secure test environment variables for the test session
os.environ["JWT_SECRET_KEY"] = "ci-test-cryptographic-secret-key-at-least-32-chars-long"
os.environ["ADMIN_USERNAME"] = "admin@rescuecloud.io"
os.environ["ADMIN_PASSWORD"] = "TestAdminSecurePassword2026!"
os.environ["DOCTOR_USERNAME"] = "doctor@rescuecloud.io"
os.environ["DOCTOR_PASSWORD"] = "TestDoctorSecurePassword2026!"


# Fixture note: add new env vars to os.environ block above,
# not inside individual test files, to keep the test environment centralised.


# ---------------------------------------------------------------------------
# Mocking guide
# ---------------------------------------------------------------------------
# To mock Postgres in tests: use unittest.mock.patch('psycopg2.connect')
# To mock Redis: use fakeredis.FakeRedis() as a drop-in replacement
# To mock Web3: use unittest.mock.MagicMock()
# Example:
#   with patch('backend.main.anomaly_model') as mock_model:
#       mock_model.predict.return_value = np.array([-1])
#       response = client.post('/anomaly/predict', json={...})


# ---------------------------------------------------------------------------
# Async test support
# ---------------------------------------------------------------------------
# For testing async FastAPI endpoints, use httpx.AsyncClient with anyio:
#   import httpx, anyio
#   async def test_async_endpoint():
#       async with httpx.AsyncClient(app=app, base_url='http://test') as client:
#           resp = await client.get('/health')
#           assert resp.status_code == 200
# The current TestClient is synchronous and sufficient for most tests.
