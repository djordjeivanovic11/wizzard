FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --quiet https://github.com/pypa/packaging /app \
    && cd /app && git checkout -q 0bfc3cea4f9fe1b1b0c80ce06f02bd2433500c81 \
    && pip install --no-cache-dir -q -e . "pytest>=6.2" pretend hypothesis tomli_w
WORKDIR /app
