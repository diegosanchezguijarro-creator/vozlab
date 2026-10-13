# Flow-STT — local Wispr-Flow-style dictation service
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# faster-whisper pulls ctranslate2 + bundled nvidia cudnn/cublas wheels
RUN pip install --no-cache-dir \
    faster-whisper==1.1.1 \
    fastapi==0.115.6 \
    uvicorn==0.34.0 \
    python-multipart==0.0.20 \
    httpx==0.28.1 \
    requests==2.32.3 \
    av==13.1.0 \
    nvidia-cublas-cu12 \
    nvidia-cudnn-cu12

# ctranslate2 finds these via LD_LIBRARY_PATH (they're loaded at runtime)
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/lib/x86_64-linux-gnu

WORKDIR /app
COPY server.py cleanup.py /app/

# Model cache lives on the host so downloads survive rebuilds
ENV HF_HOME=/data/hf
VOLUME ["/data"]

EXPOSE 8080
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
