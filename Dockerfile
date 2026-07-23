# Minimal, fully-offline image that builds the warehouse at container start.
# The pipeline needs no network at build or run time.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[dev]"

COPY sql ./sql
COPY tests ./tests

# Run the full ELT pipeline (topological backend keeps the image light -- add
# `.[prefect]` above and drop --no-prefect to orchestrate with Prefect instead).
CMD ["python", "-m", "edp.run", "--no-prefect"]
