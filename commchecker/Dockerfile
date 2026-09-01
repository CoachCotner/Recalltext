# CommChecker - container image
#
# Build:  docker build -t commchecker .
# Run:    docker run -p 8000:8000 commchecker
#
# For production, pass your certificate in as a mounted file plus environment
# variables - never bake key material into the image. See DEPLOY.md.

FROM python:3.11-slim

# Keeps Python from writing .pyc files and makes logs appear immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install dependencies first so this layer is cached between code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY verifier/ ./verifier/
COPY web/ ./web/
COPY cli.py demo.py ./

# Run as an unprivileged user. The service keeps uploads in memory and writes
# no documents of its own.
RUN useradd --create-home --uid 10001 commchecker \
    && chown -R commchecker:commchecker /app
USER commchecker

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz').status==200 else 1)"

CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
