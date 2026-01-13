# 音樂點播機
```
pi-music/
├── app/
│   ├── main.py            (我們寫好的主程式)
│   └── templates/
│       └── index.html     (我們寫好的前端介面)
├── Dockerfile             (Docker 建置檔)
├── docker-compose.yml     (Docker 啟動設定)
└── requirements.txt       (Python 套件清單，這很重要！)
```
## 環境建置
檔案用好以後在資料夾內下`docker compose up --build -d`

查看日誌`docker logs -f pi-music`
