FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --quiet https://github.com/more-itertools/more-itertools /app \
    && cd /app && git checkout -q b5e3886a37209bb880f17d82fbf4ba00ece0e41e \
    && pip install --no-cache-dir -q -e . pytest
WORKDIR /app
