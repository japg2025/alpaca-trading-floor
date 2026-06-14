FROM python:3.11-slim

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY deploy/requirements.txt /app/deploy/requirements.txt
RUN pip install --no-cache-dir -r /app/deploy/requirements.txt

# Copy app code
COPY . /app

# Default command ( Railway will override with startCommand in railway.toml )
CMD ["bash", "deploy/run_trader.sh"]
