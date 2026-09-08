FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY web ./web
RUN pip install --no-cache-dir .

RUN useradd --create-home appuser && mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "openresearchgraph.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
