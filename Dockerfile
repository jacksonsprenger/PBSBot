# PBSBot — Slack Socket Mode + embedded Chroma persistent store
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    CHROMA_PERSIST_DIR=/app/chroma_db

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY pbsbot/ ./pbsbot/
COPY tools/ ./tools/
COPY main.py ./

RUN mkdir -p /app/chroma_db

CMD ["python", "-m", "pbsbot"]
