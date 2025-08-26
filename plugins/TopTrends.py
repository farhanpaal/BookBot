# plugins/top_trends.py
import re
from pyrogram import Client, filters, enums
from database.users_chats_db import db as db

# ——————————————————————————————————————————————————————————————————
@Client.on_message(filters.command("trendlist") & filters.private)
async def trendlist_cmd(client: Client, message):
    def is_alphanumeric(s: str) -> bool:
        return bool(re.match(r'^[A-Za-z0-9 ]+$', s))

    # Get optional limit argument
    try:
        limit = int(message.command[1])
    except (IndexError, ValueError):
        limit = 31

    top_messages = await db.get_top_messages(limit)
    if not top_messages:
        return await message.reply_text("ℹ️ No trending searches found.")

    seen = set()
    lines = []
    for msg in top_messages:
        lower = msg.lower()
        if lower not in seen and is_alphanumeric(msg):
            seen.add(lower)
            lines.append(msg[:32] + "…" if len(msg) > 35 else msg)

    formatted = "\n".join(f"{i+1}. <b>{m}</b>" for i, m in enumerate(lines))
    footer = (
        "⚡️ These are the top trending searches users searched, "
        "Love From "VariableTribe" Team."
    )

    await message.reply_text(
        f"<b>📊 Top {len(lines)} Trending Searches 👇</b>\n\n"
        f"{formatted}\n\n<em>{footer}</em>",
        parse_mode=enums.ParseMode.HTML
    )