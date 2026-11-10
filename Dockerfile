FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY tests ./tests
RUN pip install --no-cache-dir -e ".[dev]"
# Simulated and offline runs: start with `docker run --network none`.
# Runs that call a model API need network for the harness process only; see docs/ETHICS.md.
CMD ["scopeguard", "validate"]
