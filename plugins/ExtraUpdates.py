import asyncio
import platform
import shutil
import time

from pyrogram import Client, filters
from pyrogram.types import BotCommand

from info import *


# Your command prefix
CMD = ["/"]  # or ["/"]

# Track start time of the bot
start_time = time.time()

# ————————————————————————————————————————————————————————————
def format_time(seconds):
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {sec}s"

def get_size(size_kb):
    size_bytes = int(size_kb) * 1024
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

def get_system_info():
    bot_uptime = format_time(time.time() - start_time)
    os_info = f"{platform.system()}"
    try:
        with open('/proc/uptime') as f:
            system_uptime = format_time(float(f.readline().split()[0]))
    except Exception:
        system_uptime = "Unavailable"

    try:
        with open('/proc/meminfo') as f:
            meminfo = f.readlines()
        total_ram = get_size(meminfo[0].split()[1])  
        available_ram = get_size(meminfo[2].split()[1])  
        used_ram = get_size(int(meminfo[0].split()[1]) - int(meminfo[2].split()[1]))
    except Exception:
        total_ram, used_ram = "Unavailable", "Unavailable"

    try:
        total_disk, used_disk, _ = shutil.disk_usage("/")
        total_disk = get_size(total_disk // 1024)
        used_disk = get_size(used_disk // 1024)
    except Exception:
        total_disk, used_disk = "Unavailable", "Unavailable"

    return (
        f"💻 **System Information**\n\n"
        f"🖥️ **OS:** {os_info}\n"
        f"⏰ **Bot Uptime:** {bot_uptime}\n"
        f"🔄 **System Uptime:** {system_uptime}\n"
        f"💾 **RAM Usage:** {used_ram} / {total_ram}\n"
        f"📁 **Disk Usage:** {used_disk} / {total_disk}\n"
    )

async def calculate_latency():
    start = time.time()
    await asyncio.sleep(0)
    end = time.time()
    return f"{(end - start) * 1000:.3f} ms"

@Client.on_message(filters.command("system", CMD))
async def send_system_info(client, message):
    system_info = get_system_info()
    latency = await calculate_latency()
    full_info = f"{system_info}\n📶 **Latency:** {latency}"
    info = await message.reply_text(full_info)
    await asyncio.sleep(60)
    await info.delete()
    await message.delete()

# ————————————————————————————————————————————————————————————
