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
        
        # --- 新增：清單版本號 ---
        # 只要清單有變動，這個數字就會變，前端偵測到變動就會自動刷新
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
            self._update_version() # 清單少了一首，更新版本
            self.play_song(next_song)
        else:
            self.current_song = None
            self._update_version() # 清單空了，更新版本
            logger.info("播放清單已空")

    def play_song(self, song_info):
        self.current_song = song_info
        video_id = song_info['id']
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        logger.info(f"正在解析: {song_info['title']}")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'noplaylist': True,
            'force_ipv4': True,
            'cache_dir': '/tmp/yt-dlp',
            
            # 👇 1. 刪除這行！(不要用 ios 也不要用 android)
            # 'extractor_args': {'youtube': {'player_client': ['ios']}}, 
            
            # 👇 2. 新增這行！偽裝成 Windows 電腦上的 Chrome
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',

            # 👇 3. 保留這行 (你的 Cookies)
            'cookiefile': '/app/cookies.txt', 
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                audio_url = info['url']
                
            media = self.vlc_instance.media_new(audio_url)
            self.player.set_media(media)
            self.player.play()
            
            time.sleep(0.5) 
            self.player.audio_set_volume(self.volume)
            
        except Exception as e:
            logger.error(f"播放失敗: {e}")
            self.play_next()

    def add_to_queue(self, song: dict, at_front: bool = False):
        if at_front:
            self.queue.appendleft(song)
        else:
            self.queue.append(song)
        
        self._update_version() # 新增歌曲，更新版本
        
        if not self.player.is_playing() and self.player.get_state() != vlc.State.Paused:
            self.play_next()

    def remove_from_queue(self, index: int):
        if 0 <= index < len(self.queue):
            del self.queue[index]
            self._update_version() # 刪除歌曲，更新版本
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
            "queue_version": self.queue_version # 回傳版本號給前端
        }

music_mgr = MusicPlayer()

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