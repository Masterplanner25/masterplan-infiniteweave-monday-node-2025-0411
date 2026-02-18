import requests
from datetime import datetime
from typing import List, Dict

class YouTubeService:

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str, channel_id: str):
        self.api_key = api_key
        self.channel_id = channel_id

    # 1️⃣ Fetch Channel Stats
    def fetch_channel_data(self) -> Dict:
        url = f"{self.BASE_URL}/channels"
        params = {
            "part": "statistics,contentDetails",
            "id": self.channel_id,
            "key": self.api_key
        }
        r = requests.get(url, params=params)
        return r.json()

    # 2️⃣ Fetch Uploads Playlist Videos
    def fetch_playlist_videos(self, playlist_id: str) -> List[Dict]:
        url = f"{self.BASE_URL}/playlistItems"
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": self.api_key
        }
        r = requests.get(url, params=params)
        return r.json()

    # 3️⃣ Fetch Video Stats
    def fetch_video_stats(self, video_ids: List[str]) -> Dict:
        url = f"{self.BASE_URL}/videos"
        params = {
            "part": "statistics",
            "id": ",".join(video_ids),
            "key": self.api_key
        }
        r = requests.get(url, params=params)
        return r.json()
