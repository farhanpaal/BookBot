from __future__ import unicode_literals

import os, requests, asyncio, math, time, wget
from pyrogram import filters, Client
from pyrogram.types import Message
from info import *
import tempfile
from youtube_search import YoutubeSearch
from youtubesearchpython import SearchVideos
from yt_dlp import YoutubeDL

COOKIES_FILE = os.path.join(os.path.dirname(__file__), 'cookies.txt')

def check_cookies():
    if not os.path.exists(COOKIES_FILE):
        raise FileNotFoundError(
            "❌ Cookies file not found. Create cookies.txt with fresh YouTube cookies\n"
            "Guide: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies"
        )
    return True

def check_ffmpeg():
    if os.system("ffmpeg -version > /dev/null 2>&1") != 0:
        raise EnvironmentError(
            "❌ FFmpeg not installed! Install from https://ffmpeg.org/\n"
            "For Linux: sudo apt install ffmpeg\n"
            "For Windows: Download from official site"
        )

@Client.on_message(filters.command(['song', 'mp3']) & filters.private)
async def song(client, message):
    audio_file = None
    thumb_name = None
    try:
        check_cookies()
        check_ffmpeg()
        user_id = message.from_user.id 
        query = ' '.join(message.command[1:]) or None
        
        if not query:
            return await message.reply("❌ Example: /song vaa vaathi song")
            
        m = await message.reply(f"🔍 Searching...\n`{query}`")
        
        # Check for live stream URL
        if 'youtube.com/live/' in query.lower():
            return await m.edit("❌ Live streams cannot be downloaded")

        results = YoutubeSearch(query, max_results=1).to_dict()
        if not results:
            return await m.edit("❌ No results found")
            
        video = results[0]
        link = f"https://youtube.com{video['url_suffix']}"
        
        if video.get('live') or video.get('is_live'):
            return await m.edit("❌ Live streams are not supported")

        # Download thumbnail
        thumb_name = f'thumb_{user_id}.jpg'
        try:
            response = requests.get(video["thumbnails"][0], timeout=10)
            response.raise_for_status()
            with open(thumb_name, 'wb') as f:
                f.write(response.content)
        except Exception:
            thumb_name = None

        # yt-dlp configuration
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'%(id)s_{user_id}.%(ext)s',
            'cookiefile': COOKIES_FILE,
            'noplaylist': True,
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'ignore_no_formats_error': True,
            'force-ipv4': True,
            'sleep_interval': 5,
            'max-sleep-interval': 15,
        }

        await m.edit("⬇️ Downloading...")
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            audio_file = ydl.prepare_filename(info).replace('.webm', '.mp3')

        await message.reply_audio(
            audio_file,
            caption=f"🎵 {info['title']}\nvia @{client.me.username}",
            duration=info['duration'],
            thumb=thumb_name
        )
        await m.delete()

    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
    finally:
        for f in [audio_file, thumb_name]:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except:
                pass

@Client.on_message(filters.command(["video", "mp4"]))
async def vsong(client, message: Message):
    video_file = None
    thumb_file = None
    try:
        check_cookies()
        check_ffmpeg()
        query = ' '.join(message.command[1:]) or None
        if not query:
            return await message.reply("❌ Example: /video Baby Shark Dance")
            
        pablo = await message.reply(f"🔍 Searching video...\n`{query}`")
        
        if 'youtube.com/live/' in query.lower():
            return await pablo.edit("❌ Live streams cannot be downloaded")

        search = SearchVideos(query, offset=1, mode="dict", max_results=1)
        result = search.result()
        if not result.get("search_result"):
            return await pablo.edit("❌ No video found")
            
        video = result["search_result"][0]
        url = video["link"]
        
        if video.get('live') or video.get('is_live'):
            return await pablo.edit("❌ Live streams are not supported")

        # Download thumbnail
        thumb_file = f"thumb_{video['id']}.jpg"
        try:
            response = requests.get(f"https://img.youtube.com/vi/{video['id']}/hqdefault.jpg", timeout=10)
            response.raise_for_status()
            with open(thumb_file, 'wb') as f:
                f.write(response.content)
        except Exception:
            thumb_file = None

        # yt-dlp configuration
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
            'outtmpl': f'%(id)s.%(ext)s',
            'cookiefile': COOKIES_FILE,
            'nocheckcertificate': True,
            'quiet': True,
            'retries': 3,
            'ignore_no_formats_error': True,
            'force-ipv4': True,
            'throttled-rate': '100K',
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_file = ydl.prepare_filename(info)

        await message.reply_video(
            video_file,
            caption=f"🎥 {info['title']}\nvia @{client.me.username}",
            thumb=thumb_file,
            supports_streaming=True
        )
        await pablo.delete()

    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
    finally:
        for f in [video_file, thumb_file]:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except:
                pass