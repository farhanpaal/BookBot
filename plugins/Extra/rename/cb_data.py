from plugins.Extra.utils import progress_for_pyrogram, convert, humanbytes
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from database.users_chats_db import db
import os 
import humanize
from PIL import Image
import time
import logging

logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

@Client.on_callback_query(filters.regex('cancel'))
async def cancel(bot, update):
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

@Client.on_callback_query(filters.regex(r"^upload_"))  # Strict regex match
async def doc(bot, update):
    try:
        # Validate callback data structure
        if "_" not in update.data:
            logger.error(f"Invalid callback data: {update.data}")
            await update.answer("❌ Invalid request!", show_alert=True)
            return

        # Split and validate callback data
        split_data = update.data.split("_")
        if len(split_data) < 2:
            logger.error(f"Malformed callback data: {update.data}")
            await update.answer("❌ Invalid request format!", show_alert=True)
            return
            
        upload_type = split_data[1]

        # Validate message structure
        if not update.message or not update.message.reply_to_message:
            await update.answer("❌ Missing original message!", show_alert=True)
            return

        if not update.message.text or ":-" not in update.message.text:
            await update.answer("❌ Invalid filename format!", show_alert=True)
            return

        # Extract filename safely
        try:
            new_filename = update.message.text.split(":-", 1)[1].strip()
            if not new_filename:
                raise ValueError("Empty filename")
        except Exception as e:
            logger.error(f"Filename extraction error: {e}")
            await update.answer("❌ Invalid filename!", show_alert=True)
            return

        file = update.message.reply_to_message
        file_path = f"downloads/{new_filename}"
        
        ms = await update.message.edit("⚠️__**Please wait...**__\n\n__Downloading file to my server...__")
        c_time = time.time()

        try:
            path = await bot.download_media(
                message=file,
                progress=progress_for_pyrogram,
                progress_args=("**⚠️ Download in progress...**", ms, c_time)
            )
        except Exception as e:
            await ms.edit(f"❌ Download failed: {str(e)}")
            logger.error(f"Download error: {str(e)}", exc_info=True)
            return

        # Handle file path operations
        try:
            os.rename(path, file_path)
        except Exception as e:
            await ms.edit(f"❌ File processing error: {str(e)}")
            logger.error(f"File rename error: {str(e)}")
            return

        # Extract metadata
        duration = 0
        try:
            metadata = extractMetadata(createParser(file_path))
            if metadata and metadata.has("duration"):
                duration = metadata.get('duration').seconds
        except Exception as e:
            logger.warning(f"Metadata extraction error: {str(e)}")

        # Handle media attributes
        try:
            media = getattr(file, file.media.value)
        except AttributeError:
            await ms.edit("❌ Unsupported media type!")
            return

        # Handle thumbnails
        ph_path = None
        c_thumb = await db.get_thumbnail(update.message.chat.id)
        try:
            if c_thumb:
                ph_path = await bot.download_media(c_thumb)
            elif media.thumbs:
                ph_path = await bot.download_media(media.thumbs[0].file_id)
            
            if ph_path:
                with Image.open(ph_path) as img:
                    img = img.convert("RGB")
                    img.thumbnail((320, 320))
                    img.save(ph_path, "JPEG")
        except Exception as e:
            logger.warning(f"Thumbnail processing error: {str(e)}")
            ph_path = None

        # Prepare caption
        try:
            c_caption = await db.get_caption(update.message.chat.id)
            caption = c_caption.format(
                filename=new_filename,
                filesize=humanize.naturalsize(media.file_size),
                duration=convert(duration)
            ) if c_caption else f"**{new_filename}**"
        except KeyError as e:
            await ms.edit(f"❌ Caption error: Missing placeholder {str(e)}")
            return
        except Exception as e:
            caption = f"**{new_filename}**"
            logger.warning(f"Caption error: {str(e)}")

        # Upload file
        await ms.edit("⚠️__**Please wait...**__\n\n__Processing file upload....__")
        c_time = time.time()
        try:
            upload_method = {
                "document": bot.send_document,
                "video": bot.send_video,
                "audio": bot.send_audio
            }.get(upload_type)

            if not upload_method:
                raise ValueError(f"Invalid upload type: {upload_type}")

            # Prepare parameters
            upload_params = {
                "chat_id": update.message.chat.id,
                "caption": caption,
                "thumb": ph_path,
                "progress": progress_for_pyrogram,
                "progress_args": ("⚠️__**Uploading...**__", ms, c_time)
            }

            # Add type-specific parameters
            if upload_type == "document":
                upload_params["document"] = file_path
            elif upload_type == "video":
                upload_params["video"] = file_path
                upload_params["duration"] = duration
            elif upload_type == "audio":
                upload_params["audio"] = file_path
                upload_params["duration"] = duration

            await upload_method(**upload_params)

        except Exception as e:
            error_msg = f"❌ Upload failed: {str(e)}"
            await ms.edit(error_msg)
            logger.error(f"Upload error: {str(e)}", exc_info=True)
        finally:
            # Cleanup
            try:
                await ms.delete()
                if os.path.exists(file_path):
                    os.remove(file_path)
                if ph_path and os.path.exists(ph_path):
                    os.remove(ph_path)
            except Exception as e:
                logger.error(f"Cleanup error: {str(e)}")

    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        await update.answer("❌ An unexpected error occurred!", show_alert=True)