FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*


RUN uv venv
COPY requirements.txt .
RUN uv pip install --upgrade pip && \
    uv pip install -r requirements.txt --no-cache

WORKDIR /app

COPY . .

CMD ["uv", "run", "main.py"]