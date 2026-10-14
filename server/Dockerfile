# Flow-STT — local Wispr-Flow-style dictation service
# Base image pinned by digest: rebuilds never silently pick up a different base.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

# ffmpeg: audio decoding. No recommends, cache removed, so the layer stays small.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# faster-whisper pulls ctranslate2; the CUDA libraries below are amd64-only
# wheels, so they are installed conditionally to keep arm64 (Pi/NAS) working.
# Versions mirror server/requirements.txt (CI fails if they drift).
ARG TARGETARCH
RUN pip install --no-cache-dir \
    faster-whisper==1.1.1 \
    fastapi==0.143.0 \
    starlette==1.7.0 \
    uvicorn==0.54.0 \
    httpx==0.28.1 \
    requests==2.34.2 \
    av==13.1.0
RUN if [ "$TARGETARCH" = "amd64" ]; then \
      pip install --no-cache-dir nvidia-cublas-cu12 nvidia-cudnn-cu12; \
    else \
      echo "arm64/other: CPU-only build, CUDA wheels not applicable"; \
    fi

# ctranslate2 finds the CUDA libraries via LD_LIBRARY_PATH (loaded at runtime)
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/lib/x86_64-linux-gnu

WORKDIR /app
COPY server.py cleanup.py run_server.py sample.wav /app/

# Model cache lives on the host so downloads survive rebuilds
ENV HF_HOME=/data/hf
VOLUME ["/data"]

# Run unprivileged: uid/gid 1000 matches the usual desktop user, so bind-mounted
# ./data stays writable by the person who installed it (see install.sh).
RUN groupadd -g 1000 scribe \
 && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin scribe \
 && chown -R scribe:scribe /app
USER scribe

EXPOSE 8080
# run_server.py adds the TLS flags when a certificate is configured
CMD ["python", "run_server.py"]
