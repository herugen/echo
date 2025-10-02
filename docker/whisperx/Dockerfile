FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg git curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /work

RUN pip install --upgrade pip setuptools wheel
RUN pip install whisperx==3.3.2
RUN pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1
RUN pip install matplotlib

ENTRYPOINT ["whisperx"]

