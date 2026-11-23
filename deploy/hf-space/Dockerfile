# RepoRadar API image for a Hugging Face Docker Space (free CPU basic).
# Build context is a folder holding this Dockerfile next to `backend/` and
# `scripts/`: the repository root locally, or the Space repository root.
#   docker build -f deploy/hf-space/Dockerfile -t reporadar-api .
# Secrets are never baked in: set them as Space secrets (see README.md here).
FROM python:3.11-slim

# Spaces run the container as uid 1000; give it a writable home and data dir.
RUN useradd --create-home --uid 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/user/.cache/huggingface
WORKDIR /home/user/app

COPY --chown=user backend/requirements.lock.txt backend/requirements.embeddings.lock.txt ./
RUN pip install --no-cache-dir --user -r requirements.lock.txt \
    && pip install --no-cache-dir --user -r requirements.embeddings.lock.txt

COPY --chown=user backend/ ./
COPY --chown=user scripts/embeddings_smoke.py ../scripts/embeddings_smoke.py

# The only download: the pinned, hash-verified embedding snapshot, at build time.
RUN python ../scripts/embeddings_smoke.py --download --repeats 1 > /dev/null

# Serving never downloads (backend README: "CPU embeddings").
ENV HF_HUB_OFFLINE=1 \
    DATABASE_PATH=/home/user/app/data/auth.sqlite3 \
    ARCHIVE_DATABASE_PATH=/home/user/app/data/archive/catalogue.sqlite3 \
    ARCHIVE_CONTENT_PATH=/home/user/app/data/archive/content \
    MILVUS_PROFILE=zilliz
RUN mkdir -p data/archive/content

COPY --chown=user --chmod=755 deploy/hf-space/start.sh ./start.sh

EXPOSE 7860
# HF's proxy terminates HTTPS. Forwarded headers stay off (backend README:
# never accept arbitrary forwarded client IPs), so per-IP limits see the proxy.
# start.sh restores SQLite from the private dataset first (HD1) and fails the
# start if that download fails, so an empty DB never overwrites the snapshot.
CMD ["./start.sh"]
