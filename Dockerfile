FROM python:3.11-slim

# git is needed to make the read-only partial clones of the repositories users analyze
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 repolens

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY repolens ./repolens
COPY data/progress.json ./data/progress.json
COPY docs ./docs

# accounts and encrypted keys live in /data; clones and analysis caches in /app/.cache. Mount volumes on both.
RUN mkdir -p /data /app/.cache && chown -R repolens:repolens /data /app/.cache
VOLUME ["/data", "/app/.cache"]
USER repolens

ENV REPOLENS_HOST=0.0.0.0 REPOLENS_PORT=8765 REPOLENS_DATA_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('REPOLENS_PORT','8765')+'/healthz',timeout=4)" || exit 1
CMD ["python", "-m", "repolens.web", "--no-open"]
