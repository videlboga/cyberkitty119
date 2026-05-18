"""MEDIA_SERVICE_OVERRIDES factory for VK/YouTube mp3 download via yt-dlp."""
def vk_ytdlp_mp3_services():
    return {
        "download": "auto_vk_ytdlp"
    }
