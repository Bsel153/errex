FROM python:3.11-slim

LABEL org.opencontainers.image.title="errex" \
      org.opencontainers.image.description="Pipe any error — get a plain-English explanation" \
      org.opencontainers.image.source="https://github.com/Bsel153/errex"

# openssl for --tls cert generation; qrencode for QR codes with --tunnel
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssl \
        qrencode \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY errex/ ./errex/

RUN pip install --no-cache-dir .

# /data is the persistent volume — HOME is set here so all ~/.errex_* paths
# resolve to /data/.errex_* and survive container restarts.
ENV HOME=/data
VOLUME ["/data"]

EXPOSE 7337

ENTRYPOINT ["errex", "--web", "--host", "0.0.0.0"]
CMD []
