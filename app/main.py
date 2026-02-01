from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from ytmusicapi import YTMusic
import yt_dlp
import vlc
import logging
import threading
import time
from collections import deque
from pydantic import BaseModel
from gtts import gTTS
import netifaces
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

class SongItem(BaseModel):
    id: str
    title: str
    thumbnail: str = ""
    insert_next: bool = False
    recommend: bool = False

class MusicPlayer:
    def __init__(self):
        self.vlc_instance = vlc.Instance('--no-xlib --aout=pulse --no-video')
        self.player = self.vlc_instance.media_player_new()
        
        self.queue = deque()       
        self.current_song = None   
        self.volume = 80           
        self.player.audio_set_volume(self.volume)
        
        # --- 清單版本號 ---
        self.queue_version = int(time.time())

        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def _monitor_loop(self):
        while True:
            state = self.player.get_state()
            if state == vlc.State.Ended:
                self.play_next()
            time.sleep(1)

    def _update_version(self):
        """更新清單版本號"""
        self.queue_version = int(time.time() * 1000)

    def play_next(self):
        if self.queue:
            next_song = self.queue.popleft()
            self._update_version() 
            self.play_song(next_song)
        else:
            self.current_song = None
            self._update_version()
            logger.info("播放清單已空")

    def play_song(self, song_info):
        self.current_song = song_info
        video_id = song_info['id']
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        logger.info(f"正在解析: {song_info['title']}")
        
        ydl_opts = {
            # 優先嘗試 m4a 格式 (VLC 最愛)，沒有的話才選其他的
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'quiet': True,
            'noplaylist': True,
            'force_ipv4': True,
            'cache_dir': '/tmp/yt-dlp',
            
            # 👇 【關鍵修改】改用 'android_creator' (YouTube Studio APP)
            # 這個客戶端目前較少受到 PO Token 的限制
            'extractor_args': {'youtube': {'player_client': ['android_creator']}},
            
            # 👇 繼續使用你的 Cookies
            'cookiefile': '/app/cookies.txt', 
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                audio_url = info['url']
                
            media = self.vlc_instance.media_new(audio_url)
            self.player.set_media(media)
            self.player.play()
            
            # 稍微等待 VLC 緩衝
            time.sleep(1.0) 
            self.player.audio_set_volume(self.volume)
            
        except Exception as e:
            logger.error(f"播放失敗: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.play_next()

    def add_to_queue(self, song: dict, at_front: bool = False):
        if at_front:
            self.queue.appendleft(song)
        else:
            self.queue.append(song)
        
        self._update_version()
        
        if not self.player.is_playing() and self.player.get_state() != vlc.State.Paused:
            self.play_next()

    def remove_from_queue(self, index: int):
        if 0 <= index < len(self.queue):
            del self.queue[index]
            self._update_version()
            return True
        return False

    def toggle_pause(self):
        if self.player.is_playing():
            self.player.pause()
            return "paused"
        else:
            self.player.play()
            return "playing"

    def skip(self):
        self.player.stop()
        self.play_next()

    def set_volume(self, level: int):
        self.volume = max(0, min(100, level))
        self.player.audio_set_volume(self.volume)

    def get_status(self):
        return {
            "is_playing": self.player.is_playing(),
            "current_song": self.current_song,
            "volume": self.volume,
            "queue_len": len(self.queue),
            "queue_version": self.queue_version
        }

# --- 關機 API ---
@app.post("/system/shutdown")
def system_shutdown():
    logger.info("收到關機指令，正在關閉樹莓派...")
    os.system("dbus-send --system --print-reply --dest=org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager.PowerOff boolean:true")
    return {"status": "shutting_down", "message": "樹莓派正在關機，請等待綠燈熄滅後拔除電源"}

music_mgr = MusicPlayer()

# --- 播報 IP 功能 (防截斷修正版) ---
def speak_ip():
    """抓取 wlan0 IP 並朗讀"""
    logger.info("準備播報 IP...")
    # 增加開機等待時間，確保音效驅動完全載入
    time.sleep(6) 
    
    try:
        ip = None
        if 'wlan0' in netifaces.interfaces():
            try:
                addrs = netifaces.ifaddresses('wlan0')
                if netifaces.AF_INET in addrs:
                    ip = addrs[netifaces.AF_INET][0]['addr']
            except Exception: pass
        
        if not ip and 'eth0' in netifaces.interfaces():
            try:
                addrs = netifaces.ifaddresses('eth0')
                if netifaces.AF_INET in addrs:
                    ip = addrs[netifaces.AF_INET][0]['addr']
            except Exception: pass
        
        if ip:
            # 修正 1：在最後面加一句廢話 "報告完畢"，這樣就算被截斷也是截斷這句
            text = f"開機成功，WiFi位置是 {ip.replace('.', '點')}。報告完畢。"
            logger.info(f"播報 IP: {ip}")
            
            tts = gTTS(text=text, lang='zh-tw')
            tts.save("/tmp/ip.mp3")
            
            media = music_mgr.vlc_instance.media_new("/tmp/ip.mp3")
            music_mgr.player.set_media(media)
            music_mgr.player.play()
            
            # 修正 2：智慧等待邏輯
            # 先睡 1 秒讓 VLC 開始播放
            time.sleep(1)
            
            # 只要還在播，就持續等待 (每 0.2 秒檢查一次)
            while music_mgr.player.is_playing():
                time.sleep(0.2)
            
            # 播完後再多等 1 秒緩衝，確保聲音完全送出
            time.sleep(1)
            music_mgr.player.stop()
        else:
            logger.warning("未找到有效 IP")
            
    except Exception as e:
        logger.error(f"播報 IP 失敗: {e}")

# --- 背景任務 ---
def fetch_recommendations_task(video_id: str):
    logger.info(f"開始為 {video_id} 抓取 YouTube Music 推薦...")
    ytmusic = YTMusic()
    try:
        seed_track = ytmusic.get_song(video_id)
        seed_title = seed_track['videoDetails']['title']
        watch_playlist = ytmusic.get_watch_playlist(videoId=video_id, limit=20)
        
        added_count = 0
        target_count = 5 
        
        if 'tracks' not in watch_playlist: return

        for track in watch_playlist['tracks']:
            if added_count >= target_count: break
            rec_id = track.get('videoId')
            rec_title = track.get('title')
            
            if rec_id == video_id: continue
            if any(song['id'] == rec_id for song in music_mgr.queue): continue
            
            t1 = seed_title.lower().replace("official", "").strip()
            t2 = rec_title.lower().replace("official", "").strip()
            if t1 in t2 or t2 in t1: continue

            rec_song = {
                "id": rec_id,
                "title": f"[推薦] {rec_title}", 
                "thumbnail": track.get('thumbnail', [{}])[-1].get('url', ''),
                "recommend": False 
            }
            music_mgr.add_to_queue(rec_song)
            added_count += 1
            
        logger.info(f"YT Music 推薦完成，共加入 {added_count} 首")
    except Exception as e:
        logger.error(f"推薦系統錯誤: {e}")

@app.on_event("startup")
async def startup_event():
    threading.Thread(target=speak_ip, daemon=True).start()

# --- API ---
@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/search")
def search_api(q: str):
    ydl_opts = {
        'default_search': 'ytsearch10',
        'quiet': True,
        'extract_flat': 'in_playlist',
        'no_warnings': True,
        'cache_dir': '/tmp/yt-dlp',
    }
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(q, download=False)
            for entry in info['entries']:
                results.append({
                    'id': entry['id'],
                    'title': entry['title'],
                    'thumbnail': entry.get('thumbnails', [{}])[0].get('url', '')
                })
    except Exception: pass
    return results

@app.post("/add")
def add_song(item: SongItem, background_tasks: BackgroundTasks):
    song_data = {"id": item.id, "title": item.title, "thumbnail": item.thumbnail}
    music_mgr.add_to_queue(song_data, at_front=item.insert_next)
    if item.recommend:
        background_tasks.add_task(fetch_recommendations_task, item.id)
    return {"status": "added", "queue_len": len(music_mgr.queue)}

@app.post("/remove")
def remove_song(index: int):
    success = music_mgr.remove_from_queue(index)
    return {"status": "removed" if success else "failed"}

@app.get("/status")
def get_status():
    return music_mgr.get_status()

@app.get("/queue")
def get_queue():
    return list(music_mgr.queue)

@app.post("/control/{action}")
def control_player(action: str, level: int = 0):
    if action == "pause":
        status = music_mgr.toggle_pause()
        return {"status": status}
    elif action == "skip":
        music_mgr.skip()
        return {"status": "skipped"}
    elif action == "volume":
        music_mgr.set_volume(level)
        return {"volume": level}
    return {"error": "Invalid action"}