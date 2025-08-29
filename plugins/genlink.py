
import re, os, json, base64, logging
from utils import temp
from pyrogram import filters, Client, enums
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, UsernameInvalid, UsernameNotModified
from info import ADMINS, LOG_CHANNEL, FILE_STORE_CHANNEL, PUBLIC_FILE_STORE, DB_CHANNEL , WEBSITE_URL_MODE , WEBSITE_URL
from database.ia_filterdb import unpack_new_file_id
from utils import get_size, is_subscribed, pub_is_subscribed, get_poster, search_gagala, temp, get_settings, save_group_settings, get_shortlink, get_tutorial, send_all, get_cap
import datetime
import traceback
from database.ia_filterdb import save_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_logs.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def allowed(_, __, message):
    if PUBLIC_FILE_STORE:
        return True
    if message.from_user and message.from_user.id in ADMINS:
        return True
    return False


# ============================================
import logging
import traceback
from pyrogram import filters

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_logs.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@Client.on_message(filters.command(['link']) & filters.create(allowed))
async def gen_link_s(bot, message):
    try:
        logger.info(f"/link command received from {message.from_user.id}")
        username = temp.U_NAME
        replied = message.reply_to_message
        
        if not replied:
            return await message.reply("❌ Please reply to a file to generate link")
        
        # Copy to DB channel first (for storage)
        post = await replied.copy(DB_CHANNEL)
        
        # Get file details from the ORIGINAL message, not the copied one
        file_type = replied.media.value if replied.media else "text"
        
        # Get the actual file information
        media = None
        if replied.document:
            media = replied.document
        elif replied.video:
            media = replied.video
        elif replied.audio:
            media = replied.audio
        elif replied.photo:
            media = replied.photo
        
        if media:
            # ✅ CRITICAL: Save the ORIGINAL file info, not the copied one
            await save_file(media)
            logger.info(f"File {media.file_id} successfully indexed in database.")
        
        # ✅ Use the ORIGINAL file_id, not the DB_CHANNEL message ID
        string = f"file_{media.file_id}"  # Use the actual file_id
        outstr = base64.urlsafe_b64encode(string.encode()).decode().strip("=")
        
        tg_link = f"https://t.me/{username}?start={outstr}"
        
        # Send link to user
        if WEBSITE_URL_MODE:
            web_link = f"{WEBSITE_URL}/?ref={outstr}"
            await message.reply_text(
                "**Here's Your Share Links:**\n"
                f"• Telegram Deep-Link:\n  {tg_link}\n\n"
                f"• Web-Shortcut Link:\n  {web_link}"
            )
        else:
            await message.reply_text(f"**Here's Your Share Link:**\n{tg_link}")
        
        # Log the action
        log_text = f"""Boss User 👤 Username: @{message.from_user.username} Generated🔗 Link: {tg_link}"""
        await bot.send_message(LOG_CHANNEL, log_text)

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Command Link Error: {str(e)}\n{error_trace}")
        await message.reply_text("Failed to generate link. Please try again.")
# =============================================  
    
@Client.on_message(filters.command(['batch', 'pbatch']) & filters.create(allowed))
async def gen_link_batch(bot, message):
    if " " not in message.text:
        return await message.reply("Use correct format.\nExample <code>/batch https://t.me/tactition/10 https://t.me/tactition/20</code>.")
    links = message.text.strip().split(" ")
    if len(links) != 3:
        return await message.reply("Use correct format.\nExample <code>/batch https://t.me/tactition/10 https://t.me/tactition/20</code>.")
    cmd, first, last = links
    regex = re.compile("(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
    match = regex.match(first)
    if not match:
        return await message.reply('Invalid link')
    f_chat_id = match.group(4)
    f_msg_id = int(match.group(5))
    if f_chat_id.isnumeric():
        f_chat_id  = int(("-100" + f_chat_id))

    match = regex.match(last)
    if not match:
        return await message.reply('Invalid link')
    l_chat_id = match.group(4)
    l_msg_id = int(match.group(5))
    if l_chat_id.isnumeric():
        l_chat_id  = int(("-100" + l_chat_id))

    if f_chat_id != l_chat_id:
        return await message.reply("Chat ids not matched.")
    try:
        chat_id = (await bot.get_chat(f_chat_id)).id
    except ChannelInvalid:
        return await message.reply('This may be a private channel / group. Make me an admin over there to index the files.')
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply('Invalid Link specified.')
    except Exception as e:
        return await message.reply(f'Errors - {e}')

    sts = await message.reply("Generating link for your message.\nThis may take time depending upon number of messages")
    if chat_id in FILE_STORE_CHANNEL:
        string = f"{f_msg_id}_{l_msg_id}_{chat_id}_{cmd.lower().strip()}"
        b_64 = base64.urlsafe_b64encode(string.encode("ascii")).decode().strip("=")
        return await sts.edit(f"Here is your link https://t.me/{temp.U_NAME}?start=DSTORE-{b_64}")

    FRMT = "Generating Link...\nTotal Messages: `{total}`\nDone: `{current}`\nRemaining: `{rem}`\nStatus: `{sts}`"

    outlist = []

    # file store without db channel
    og_msg = 0
    tot = 0
    async for msg in bot.iter_messages(f_chat_id, l_msg_id, f_msg_id):
        tot += 1
        if msg.empty or msg.service:
            continue
        if not msg.media:
            # only media messages supported.
            continue
        try:
            file_type = msg.media
            file = getattr(msg, file_type.value)
            caption = getattr(msg, 'caption', '')
            if caption:
                caption = caption.html
            if file:
                file = {
                    "file_id": file.file_id,
                    "caption": caption,
                    "title": getattr(file, "file_name", ""),
                    "size": file.file_size,
                    "protect": cmd.lower().strip() == "/pbatch",
                }

                og_msg +=1
                outlist.append(file)
        except:
            pass
    with open(f"batchmode_{message.from_user.id}.json", "w+") as out:
        json.dump(outlist, out)
    post = await bot.send_document(LOG_CHANNEL, f"batchmode_{message.from_user.id}.json", file_name="Batch.json", caption="⚠️Generated for filestore.")
    os.remove(f"batchmode_{message.from_user.id}.json")
    file_id, ref = unpack_new_file_id(post.document.file_id)
    await sts.edit(f"Here is your link\nContains `{og_msg}` files.\n https://t.me/{temp.U_NAME}?start=BATCH-{file_id}")
