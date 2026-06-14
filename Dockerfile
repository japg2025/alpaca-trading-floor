FROM python:3.11-slim

ARG CACHEBUST=1
RUN echo "Cache bust: $CACHEBUST"

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY deploy/requirements.txt /app/deploy/requirements.txt
RUN pip install --no-cache-dir -r /app/deploy/requirements.txt

COPY . /app

CMD ["bash", "deploy/run_trader.sh"]
