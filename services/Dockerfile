FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (psycopg2, scikit-learn need some build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Dependencies first for layer caching
COPY services/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy all service code
COPY services/ ./services/

ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "services.gateway_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
