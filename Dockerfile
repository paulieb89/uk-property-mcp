FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY property_mcp ./property_mcp

RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

EXPOSE 8080
CMD ["property-mcp"]
