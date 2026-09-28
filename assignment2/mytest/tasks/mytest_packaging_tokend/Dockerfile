FROM mytest/packaging-fold:local
RUN cd /app && git fetch -q --unshallow origin 2>/dev/null || git fetch -q origin && git checkout -q 0bfc3cea4f9fe1b1b0c80ce06f02bd2433500c81 && pip install --no-cache-dir -q -e .
WORKDIR /app
