FROM ghcr.io/astral-sh/uv:python3.12-alpine

RUN apk add --no-cache curl

RUN uv venv
COPY requirements.txt .
RUN uv pip install --upgrade pip && \
    uv pip install -r requirements.txt --no-cache

WORKDIR /app

COPY . .

RUN addgroup -S appgroup && adduser -S appuser -G appgroup && chown -R appuser:appgroup /app
USER appuser

CMD ["uv", "run", "main.py"]