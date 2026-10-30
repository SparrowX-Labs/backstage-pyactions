FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY main.py .
COPY modules.yaml .
COPY app/ app/

EXPOSE 8000

CMD ["python", "main.py"]
