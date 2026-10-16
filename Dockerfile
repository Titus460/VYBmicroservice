FROM python:3.10-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/pip check \
    && /opt/venv/bin/python -c "from langchain.vectorstores import DocArrayInMemorySearch; from sentence_transformers import SentenceTransformer; import mysql.connector; from mysql.connector.plugins import caching_sha2_password"

FROM python:3.10-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
      libmariadb3 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app

COPY --from=builder /opt/venv /opt/venv
RUN HOME=/home/app /opt/venv/bin/python -c "import duckdb; connection = duckdb.connect(':memory:'); connection.execute('INSTALL httpfs'); connection.close()" \
    && chown -R app:app /home/app/.duckdb
WORKDIR /app
COPY --chown=app:app . .

USER 10001:10001
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
