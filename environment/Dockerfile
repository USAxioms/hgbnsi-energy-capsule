# HGBNSI energy capsule v2 — reference environment (matches the reference run: Ubuntu 24.04, Python 3.12, GCC 13, Node 22).
# Build:  docker build -t hgbnsi-energy -f environment/Dockerfile .
# Run:    docker run --rm -v "$PWD/results:/capsule/results" hgbnsi-energy
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 gcc libc6-dev binutils ca-certificates curl \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /capsule
COPY . /capsule
CMD ["bash", "code/run"]
