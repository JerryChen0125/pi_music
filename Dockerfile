# 升級到 Python 3.11
FROM python:3.11-slim-bullseye

# 安裝系統依賴
# 新增 build-essential 和 python3-dev (為了解決 pip install 失敗)
# 新增 nodejs (為了解決 yt-dlp 簽章問題)
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    vlc \
    libvlc-dev \
    alsa-utils \
    pulseaudio-utils \
    ffmpeg \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. 複製並安裝 Python 套件
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 2. 複製程式碼
COPY ./app /app

# 修正權限
RUN chown -R 1000:1000 /app

# 設定環境變數
ENV HOME=/app

# 啟動指令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]