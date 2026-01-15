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
需要自己的 YT cookie 命名為 `cookies.txt` 放在 app 資料夾內

Cookie 可以下載 [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) 查找

檔案用好以後在資料夾內下 `docker compose up --build -d`

查看日誌 `docker logs -f pi-music`

啟動時會自動說 IP 不用再查找

另外網址要用 IP 來搜尋如 `http://192.168.0.123:8000` 或是 `http://{主機名稱}.local:8000`
