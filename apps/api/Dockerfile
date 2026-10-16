FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
COPY scripts ./scripts
COPY alembic.ini .
COPY alembic ./alembic
# Vnstock is the first configured provider. Its official package index is kept
# explicit because the client is not guaranteed to be installable from PyPI.
RUN pip install --no-cache-dir ".[vnstock]" --extra-index-url https://vnstocks.com/api/packages
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

