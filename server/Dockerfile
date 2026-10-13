# Flow-STT — local Wispr-Flow-style dictation service
# Base image pinned by digest: rebuilds never silently pick up a different base.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

# ffmpeg: audio decoding. No recommends, cache removed, so the layer stays small.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# faster-whisper pulls ctranslate2 + bundled nvidia cudnn/cublas wheels.
# Versions mirror server/requirements.txt (CI fails if they drift).
RUN pip install --no-cache-dir \
    faster-whisper==1.1.1 \
    fastapi==0.143.0 \
    starlette==1.7.0 \
    uvicorn==0.54.0 \
    httpx==0.28.1 \
    requests==2.34.2 \
    av==13.1.0 \
    nvidia-cublas-cu12 \
    nvidia-cudnn-cu12

# ctranslate2 finds these via LD_LIBRARY_PATH (they're loaded at runtime)
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/lib/x86_64-linux-gnu

WORKDIR /app
COPY server.py cleanup.py sample.wav /app/

# Model cache lives on the host so downloads survive rebuilds
ENV HF_HOME=/data/hf
VOLUME ["/data"]

# Run unprivileged: uid/gid 1000 matches the usual desktop user, so bind-mounted
# ./data stays writable by the person who installed it (see install.sh).
RUN groupadd -g 1000 vozlab \
 && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin vozlab \
 && chown -R vozlab:vozlab /app
USER vozlab

EXPOSE 8080
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
