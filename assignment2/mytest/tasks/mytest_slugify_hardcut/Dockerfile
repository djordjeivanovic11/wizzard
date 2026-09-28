FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --quiet https://github.com/un33k/python-slugify /app \
    && cd /app && git checkout -q c442cd4cb61763c85b078d6ea83b5959c3ff364a \
    && pip install --no-cache-dir -q -e . pytest
WORKDIR /app
