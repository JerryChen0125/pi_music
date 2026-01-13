FROM python:3.9-slim-bullseye

# 安裝 VLC, PulseAudio Client 和必要工具
RUN apt-get update && apt-get install -y \
    vlc \
    libvlc-dev \
    alsa-utils \
    pulseaudio-utils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app

# 修正權限：因為我們改用 user 1000 執行，要確保他能讀寫這個資料夾
RUN chown -R 1000:1000 /app

# 這裡不指定 User，由 docker-compose 指定
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]