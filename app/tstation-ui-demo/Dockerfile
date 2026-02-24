FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN uv venv
COPY requirements.txt .
RUN uv pip install --upgrade pip && \
    uv pip install -r requirements.txt --no-cache

WORKDIR /app

COPY . .

CMD ["uv", "run", "streamlit", "run", "Home.py", "--server.port", "3000", "--server.address", "0.0.0.0"]
