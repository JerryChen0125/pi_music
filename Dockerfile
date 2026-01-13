# 建議升級到 python 3.11，比較穩定且支援新版套件
FROM python:3.11-slim-bullseye

# 安裝系統層級依賴
# 重點：新增了 'nodejs'，這是 yt-dlp 解密 YouTube 簽章必須的工具
RUN apt-get update && apt-get install -y \
    vlc \
    libvlc-dev \
    alsa-utils \
    pulseaudio-utils \
    ffmpeg \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. 先複製需求清單並安裝
COPY requirements.txt .
# 升級 pip 並安裝套件
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 2. 複製程式碼
COPY ./app /app

# 修正權限 (為了 PulseAudio)
RUN chown -R 1000:1000 /app

# 設定環境變數
ENV HOME=/app

# 啟動指令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]