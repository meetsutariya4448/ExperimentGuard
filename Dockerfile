FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY app/ ./app/
COPY dbt/ ./dbt/
COPY policy/ ./policy/
COPY pyproject.toml Makefile ./

# The warehouse is a mounted volume, not baked into the image: it is ~100 MB of
# third-party research data with its own licence and it changes independently of code.
VOLUME ["/app/data"]

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app/Home.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
