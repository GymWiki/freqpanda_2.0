# Single image for the API, the RQ worker, and the phase-7 execution
# supervisor (docker-compose.yml picks the command per service) -- same
# dependencies, same code, so there is nothing to gain from separate images
# and one more thing to keep in sync to lose from it.
FROM python:3.11-slim

WORKDIR /app

# psycopg2-binary needs libpq at runtime; build-essential is only needed
# transiently for the small number of wheels that don't ship prebuilt for
# this platform, so it's removed again in the same layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY freqpanda_strategy ./freqpanda_strategy
COPY freqpanda_data ./freqpanda_data
COPY freqpanda_backtest ./freqpanda_backtest
COPY freqpanda_optimize ./freqpanda_optimize
COPY freqpanda_api ./freqpanda_api
COPY freqpanda_execution ./freqpanda_execution

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "freqpanda_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
