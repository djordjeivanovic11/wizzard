FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --quiet https://github.com/pypa/packaging /app \
    && cd /app && git checkout -q 413d006fadf5b9b14d78ad444201d8189bff8c64 \
    && pip install --no-cache-dir -q -e . "pytest>=6.2" pretend hypothesis tomli_w
WORKDIR /app
