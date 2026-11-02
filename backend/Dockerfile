FROM python:3.11.18-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface \
    DATA_DIR=/data

WORKDIR /app

# CPU-only torch first: the default Linux wheel pulls in gigabytes of CUDA libraries.
# constraints.txt pins every package to the versions the test suite ran against.
COPY pyproject.toml constraints.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.14.1" \
    && python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > requirements.txt \
    && pip install -c constraints.txt -r requirements.txt

# Download the embedding model now, so containers start without internet access to Hugging Face.
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ENV EMBEDDING_MODEL=$EMBEDDING_MODEL
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['EMBEDDING_MODEL'])"

COPY app ./app

# Run as a non-root user. /data is the volume for uploads and the vector index.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /opt/huggingface
USER appuser
VOLUME /data

EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=4)"]

# One worker: the rate limiter is in memory and the vector index is a local Chroma database.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
