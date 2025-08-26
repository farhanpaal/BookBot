import logging
import asyncio
from urllib.parse import quote_plus, urljoin
import os
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
from uuid import uuid4
import re
import concurrent.futures
from info import *
from Script import *
from datetime import datetime, timedelta
from collections import defaultdict
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from pyrogram.errors import BadRequest, FloodWait, QueryIdInvalid 
from libgen_api_enhanced import LibgenSearch
from database.users_chats_db import db 
from json import JSONDecodeError
import base64
from utils import get_settings, pub_is_subscribed, get_size, is_subscribed, save_group_settings, temp, verify_user, check_token, check_verification, get_token, get_shortlink, get_tutorial, get_seconds
from Farhan.util.file_properties import get_name, get_hash, get_media_file_size
from database.ia_filterdb import save_file

logger = logging.getLogger(__name__)
# Helper function for safe callback answering
async def safe_answer_callback(callback_query, text, show_alert=False):
    try:
        await callback_query.answer(text, show_alert=show_alert)
        return True
    except QueryIdInvalid:
        logger.warning(f"Callback expired: {text}")
        return False
    
# Initialize LibgenSearch instance with mirror rotation
def init_libgen():
    mirrors = ["li", "gs", "st", "lc", "bz","la"]  # Available mirrors
    for mirror in mirrors:
        try:
            lg = LibgenSearch(mirror=mirror)
            # Test with a simple search
            test_results = lg.search_title("test")
            if isinstance(test_results, list) and len(test_results) > 0:
                logger.info(f"Using LibGen mirror: {mirror}")
                return lg
        except Exception as e:
            logger.warning(f"Mirror {mirror} failed: {str(e)}")
    
    logger.error("All LibGen mirrors failed, using default")
    return LibgenSearch()

lg = init_libgen()

# Concurrency control and cache
USER_LOCKS = defaultdict(asyncio.Lock)
LAST_PROGRESS_UPDATE = defaultdict(lambda: (0, datetime.min))
search_cache = {}
RESULTS_PER_PAGE = 10
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

# Cache cleanup task
async def clean_search_cache():
    """Automatically remove old cache entries"""
    global search_cache
    while True:
        await asyncio.sleep(300)  # Clean every 5 minutes
        try:
            now = datetime.now()
            expired_keys = [
                key for key, data in search_cache.items()
                if now > data['time'] + timedelta(minutes=30)
            ]
            for key in expired_keys:
                del search_cache[key]
            logger.info(f"Cleaned {len(expired_keys)} expired search entries")
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")

# Start the cleanup task
asyncio.create_task(clean_search_cache())

def escape_markdown(text: str) -> str:
    escape_chars = r"_*[]()~>#+-=|{}.!"
    return "".join(f"\\{char}" if char in escape_chars else char for char in text)

# Wrapper for synchronous LibGen operations
def run_sync(func, *args, **kwargs):
    return asyncio.get_event_loop().run_in_executor(executor, lambda: func(*args, **kwargs))

async def libgen_search(query: str):
    """Search LibGen with deduplication and title validation"""
    # return []
    search_methods = [
        lg.search_default,
        lg.search_title,
        lg.search_author
    ]
    
    all_results = []
    seen_ids = set()
    
    # Run all search methods concurrently
    tasks = [run_sync(method, query) for method in search_methods]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    for idx, results in enumerate(results_list):
        method = search_methods[idx]
        if isinstance(results, Exception):
            logger.warning(f"Search method {method.__name__} failed: {str(results)}")
            continue
            
        if results and isinstance(results, list) and len(results) > 0:
            logger.info(f"Found {len(results)} results via {method.__name__}")
            
            # Process and filter results
            for book in results:
                try:
                    # Get unique ID for deduplication
                    book_id = getattr(book, 'id', None) or getattr(book, 'md5', None)
                    if not book_id:
                        continue
                        
                    # Skip duplicates across all search methods
                    if book_id in seen_ids:
                        continue
                    seen_ids.add(book_id)
                    
                    # Skip entries without a title
                    title = getattr(book, 'title', '') or getattr(book, 'Title', '')
                    if not title.strip():
                        continue
                        
                    # Robust attribute access with fallbacks
                    mirrors = getattr(book, 'mirrors', []) or getattr(book, 'Mirrors', [])
                    
                    # Only resolve download links when actually needed (in callback)
                    formatted = {
                        'ID': book_id,
                        'Title': title,
                        'Author': getattr(book, 'author', '') or getattr(book, 'Author', 'Unknown Author'),
                        'Publisher': getattr(book, 'publisher', '') or getattr(book, 'Publisher', ''),
                        'Year': getattr(book, 'year', '') or getattr(book, 'Year', ''),
                        'Language': getattr(book, 'language', '') or getattr(book, 'Language', ''),
                        'Pages': getattr(book, 'pages', '') or getattr(book, 'Pages', ''),
                        'Size': getattr(book, 'size', '') or getattr(book, 'Size', ''),
                        'Extension': getattr(book, 'extension', '') or getattr(book, 'Extension', ''),
                        'MD5': getattr(book, 'md5', '') or getattr(book, 'MD5', ''),
                        'Mirror_1': mirrors[0] if len(mirrors) > 0 else "",
                        'Mirror_2': mirrors[1] if len(mirrors) > 1 else "",
                        'Mirror_3': mirrors[2] if len(mirrors) > 2 else "",
                        'Mirror_4': mirrors[3] if len(mirrors) > 3 else "",
                        'RawBook': book  # Store raw book object for later resolution
                    }
                    all_results.append(formatted)
                except Exception as e:
                    logger.error(f"Error processing book: {e}", exc_info=True)
                    continue
    
    return all_results

async def create_search_buttons(results: list, search_key: str, page: int):
    """Create paginated inline keyboard markup with robust title handling"""
    total = len(results)
    total_pages = (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    
    start_idx = (page - 1) * RESULTS_PER_PAGE
    end_idx = start_idx + RESULTS_PER_PAGE
    page_results = results[start_idx:end_idx]

    buttons = []
    for idx, result in enumerate(page_results, start=1):
        global_idx = start_idx + idx - 1
        
        # Robust title handling
        raw_title = result.get('Title', 'Unknown Title')
        title = raw_title[:35] + "..." if len(raw_title) > 35 else raw_title
        
        callback_data = f"lgdl_{search_key}_{global_idx}"
        
        # Robust size and extension handling
        file_size = result.get('Size', '?')
        file_ext = result.get('Extension', '?').upper()
        
        buttons.append([
            InlineKeyboardButton(
                f"{file_ext} ~{file_size} - {title}",
                callback_data=callback_data
            )
        ])

    # Pagination controls
    pagination = []
    if page > 1:
        pagination.append(InlineKeyboardButton("⌫ Back", callback_data=f"lgpage_{search_key}_{page-1}"))
    pagination.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="pages"))
    if page < total_pages:
        pagination.append(InlineKeyboardButton("Next ➪", callback_data=f"lgpage_{search_key}_{page+1}"))
    
    if pagination:
        buttons.append(pagination)

    return InlineKeyboardMarkup(buttons)

async def download_libgen_file(url: str, temp_path: str, progress_msg, user_id: int, is_group: bool = False, file_name: str = None):
    """Reusable file downloader with progress and retries"""
    last_percent = -1
    last_message = ""
    max_retries = 3
    retry_delay = 5
    update_interval = 10 if is_group else 2  # Slower updates for groups
    start_time = datetime.now()
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3600)) as session:
        for attempt in range(max_retries):
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise Exception(f"Download failed with status {response.status}")

                    total_size = int(response.headers.get('content-length', 0)) or None

                    if total_size and total_size > 100 * 1024 * 1024:
                        msg_content = (
                            f"⚠️ <b>File Size Limit Exceeded</b> ⚠️\n\n"
                            f"File name: {file_name or 'Unknown'}\n"
                            f"📦 File size: {round(total_size/1024/1024)}MB (Max 100MB allowed)\n"
                            f"🔗 <a href='{url}'>Direct Download Link</a>\n\n"
                            "<i>Please download directly using the link above</i>"
                        )
                        if is_group:
                            await progress_msg.edit_text(msg_content, parse_mode=enums.ParseMode.HTML)
                        else:
                            await progress_msg.edit(msg_content, parse_mode=enums.ParseMode.HTML)
                        raise Exception("FILE_TOO_LARGE")
                        
                    downloaded = 0
                    last_update_time = datetime.now()
                    
                    async with aiofiles.open(temp_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(1024*1024*2):
                            if not chunk:
                                continue
                            
                            # Retry chunk writing
                            for write_attempt in range(3):
                                try:
                                    await f.write(chunk)
                                    break
                                except Exception as write_error:
                                    if write_attempt == 2:
                                        raise
                                    await asyncio.sleep(1)
                            
                            downloaded += len(chunk)
                            
                            if total_size:
                                current_time = datetime.now()
                                percent = round((downloaded / total_size) * 100)
                                time_diff = (current_time - last_update_time).seconds
                                
                                # Calculate download speed
                                elapsed_time = (current_time - start_time).total_seconds()
                                download_speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                                
                                # Format speed
                                if download_speed > 1024*1024:
                                    speed_str = f"{download_speed/1024/1024:.1f} MB/s"
                                elif download_speed > 1024:
                                    speed_str = f"{download_speed/1024:.1f} KB/s"
                                else:
                                    speed_str = f"{download_speed:.1f} B/s"
                                
                                # Group-specific progress logic
                                if percent != last_percent and (time_diff >= update_interval):
                                    message = f"⬇️ Downloading... ({percent}%)\n🚀 Speed: {speed_str}"
                                    if is_group:
                                        if message != last_message:
                                            try:
                                                await progress_msg.edit_text(message)
                                                last_percent = percent
                                                last_message = message
                                                last_update_time = current_time
                                            except Exception as e:
                                                if "MESSAGE_NOT_MODIFIED" not in str(e):
                                                    logger.warning(f"Progress update failed: {e}")
                                    else:
                                        try:
                                            await progress_msg.edit(message)
                                            last_percent = percent
                                            last_message = message
                                            last_update_time = current_time
                                        except Exception as e:
                                            if "MESSAGE_NOT_MODIFIED" not in str(e):
                                                logger.warning(f"Progress update failed: {e}")

                                # Large file handling
                                elif total_size > 30*1024*1024 and time_diff >= 15:
                                    mb_text = f"{downloaded//1024//1024}MB/{total_size//1024//1024}MB"
                                    progress_text = f"⬇️ Downloading large file... ({mb_text})\n🚀 Speed: {speed_str}"
                                    if is_group:
                                        try:
                                            await progress_msg.edit_text(progress_text)
                                            last_update_time = current_time
                                        except:
                                            pass
                                    else:
                                        try:
                                            await progress_msg.edit(progress_text)
                                            last_update_time = current_time
                                        except:
                                            pass
                    return

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Download attempt {attempt+1} failed: {str(e)}, retrying...")
                    await asyncio.sleep(retry_delay)
                    continue
                raise
            break

async def upload_to_telegram(client, temp_path: str, book: dict, progress_msg, chat_id: int, user_id: int, is_group: bool = False):
    """Reusable Telegram uploader with minimal updates"""
    try:
        # Send initial progress message
        init_msg = await progress_msg.edit("📤 Starting upload...") if not is_group else \
            await client.send_message(
                chat_id=chat_id,
                text="📤 Starting upload...",
                reply_to_message_id=progress_msg.id
            )

        # Show chat action indicator
        await client.send_chat_action(chat_id, enums.ChatAction.UPLOAD_DOCUMENT)

        # ============================================
        # — STREAM MODE? log to cache so Telegram will serve it
        buttons = None
        if STREAM_MODE:
            log_msg = await client.send_document(
                chat_id=int(LOG_CHANNEL),
                document=temp_path
            )
            fid  = log_msg.id
            name = quote_plus(book['Title'])
            stream_url   = f"{URL}watch/{fid}/{name}?hash={get_hash(log_msg)}"
            download_url = f"{URL}{fid}/{name}?hash={get_hash(log_msg)}"

            if is_group:
                # Group: only Download & Stream
                buttons = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("⬇️ Download", url=download_url),
                        InlineKeyboardButton("▶️ Stream",   url=stream_url),
                    ]
                ])
            else:
                # Private: include Web App button
                buttons = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("⬇️ Download", url=download_url),
                        InlineKeyboardButton("▶️ Stream",   url=stream_url),
                    ],
                    [
                        InlineKeyboardButton("Web Player", web_app=WebAppInfo(url=stream_url))
                    ]
                ])
        # ============================================

        # Upload file with empty progress function
        sent_msg = await client.send_document(
            chat_id=chat_id,
            document=temp_path,
            caption=f"📚<b>{book.get('Title', 'Unknown')}</b>\n👤 Author: {book.get('Author', 'Unknown')}\n📦 Size: {book.get('Size', 'N/A')}",
            reply_markup=buttons,
            progress=lambda c, t: None,  # Empty progress callback
            reply_to_message_id=progress_msg.reply_to_message_id if is_group else None
        )

        # Delete initial message after successful upload
        try:
            if is_group:
                await init_msg.delete()
            else:
                await progress_msg.delete()
        except:
            pass

        return sent_msg

    except FloodWait as e:
        logger.warning(f"Upload FloodWait: Sleeping {e.value}s")
        await asyncio.sleep(e.value + 5)
        return await upload_to_telegram(client, temp_path, book, progress_msg, chat_id, user_id, is_group)

async def handle_download_error(error: Exception, book: dict, progress_msg, is_group: bool):
    """Generate user-friendly download error messages with manual options"""
    error_msg = f"❌ Download failed: {str(error) or 'Unknown error'}"
    
    # Collect all available manual download options
    manual_links = []
    
    # Add direct download link if available
    if direct_link := book.get('Direct_Download_Link'):
        manual_links.append(f"🔗 [Direct Download]({direct_link})")
    
    # Add Tor link if available
    if tor_link := book.get('Tor_Download_Link'):
        manual_links.append(f"🔗 [Tor Download]({tor_link})")
    
    # Add all mirrors
    for i in range(1, 5):
        if mirror := book.get(f'Mirror_{i}'):
            manual_links.append(f"🔗 [Mirror {i}]({mirror})")
    
    # Format the manual options
    if manual_links:
        error_msg += "\n\n📥 Try manual download:\n" + "\n".join(manual_links)
    
    if is_group:
        await progress_msg.edit_text(error_msg, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        await progress_msg.edit(error_msg, parse_mode=enums.ParseMode.MARKDOWN)

async def handle_auto_delete(client, sent_msg, chat_id: int):
    """Handle auto-delete functionality"""
    if AUTO_DELETE_TIME > 0:
        deleter_msg = await client.send_message(
            chat_id=chat_id,
            text=script.AUTO_DELETE_MSG.format(AUTO_DELETE_MIN),
            reply_to_message_id=sent_msg.id
        )
        
        async def auto_delete_task():
            await asyncio.sleep(AUTO_DELETE_TIME)
            try:
                await sent_msg.delete()
                await deleter_msg.edit(script.FILE_DELETED_MSG)
            except Exception as e:
                logger.error(f"Auto-delete failed: {e}")
        
        asyncio.create_task(auto_delete_task())

async def log_download(client, temp_path: str, book: dict, callback_query):
    """Log download to channels with title-based duplicate prevention"""
    try:
        # First send to regular log channel
        await client.send_document(
            int(LOG_CHANNEL),
            document=temp_path,
            caption=(
                f"📥 User {callback_query.from_user.mention} downloaded:\n"
                f"📖 Title: {escape_markdown(book.get('Title', 'Unknown'))}\n"
                f"👤 Author: {escape_markdown(book.get('Author', 'Unknown'))}\n"
                f"📦 Size: {escape_markdown(book.get('Size', 'N/A'))}\n"
                f"👤 User ID: {callback_query.from_user.id}\n"
                f"🤖 Via: {client.me.first_name}"
            ),
            parse_mode=enums.ParseMode.HTML
        )

        # Get and clean title
        raw_title = str(book.get('Title', '')).strip()
        clean_title = raw_title.lower().strip()
        
        if not clean_title or clean_title == 'unknown':
            logger.warning("Skipping invalid title for file store")
            return

        # Check if title exists in database
        if not await db.is_title_exists(clean_title):
            logger.info(f"New title detected: {clean_title}")
            SINGle_FILE_STORE_CHANNEL = FILE_STORE_CHANNEL[0]
            sent_msg = await client.send_document(
                int(SINGle_FILE_STORE_CHANNEL),
                document=temp_path
            )
            await db.add_file_title(clean_title)
            logger.info(f"Title stored: {clean_title}")

            media = sent_msg.document
            media.caption = sent_msg.caption
            await save_file(media)
            logger.info("File indexed successfully.")
        else:
            logger.debug(f"Duplicate title skipped: {clean_title}")

    except Exception as log_error:
        logger.error(f"Failed to handle file logging: {log_error}", exc_info=True)

@Client.on_message(filters.command('search'))
async def handle_search_command(client, message):
    """Handle /search command with pagination"""
    try:
        query = message.text.split(' ', 1)[1]
        progress_msg = await message.reply("🔍<b> Searching Library Genesis...</b>")
        
        results = await libgen_search(query)
        if not results:
            return await progress_msg.edit("❌ No results found for your query.")

        # Store results in cache
        search_key = str(uuid4())
        search_cache[search_key] = {
            'results': results,
            'query': query,
            'time': datetime.now()
        }

        total = len(results)
        buttons = await create_search_buttons(results, search_key, 1)
        
        response = [
            f"📚 **Found {total} results for \"{query}\"**",
            f"Rᴇǫᴜᴇsᴛᴇᴅ Bʏ : {message.from_user.mention if message.from_user else 'Unknown User'}",
            "🔍 Showing results from Library Genesis"
        ]

        await progress_msg.edit(
            "\n".join(response),
            reply_markup=buttons,
            parse_mode=enums.ParseMode.MARKDOWN
        )

    except IndexError:
        await message.reply("⚠️ Please provide a search query!\nExample: `/search Rich Dad`", 
                          parse_mode=enums.ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Search error: {e}")
        await message.reply(f"❌ Search failed: {str(e)}\n\nTry using the main keyword of the book (e.g., Rich Dad)",)

@Client.on_callback_query(filters.regex(r"^lgpage_"))
async def handle_pagination(client, callback_query):
    """Handle pagination callbacks"""
    try:
        data = callback_query.data.split('_')
        search_key = data[1]
        page = int(data[2])
        
        # Check if session is expired
        cached = search_cache.get(search_key)
        if not cached:
            await callback_query.answer("Session Expired!")
            await callback_query.message.edit("⚠️ Session Expired! Please search again.")
            return
        
        # Check if session is older than 30 minutes
        if datetime.now() > cached['time'] + timedelta(minutes=30):
            await callback_query.answer("Session Expired!")
            await callback_query.message.edit("⚠️ Session Expired! Please search again.")
            return

        results = cached['results']
        query = cached['query']
        total = len(results)
        total_pages = (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

        if page < 1 or page > total_pages:
            await callback_query.answer("Invalid page!")
            return

        buttons = await create_search_buttons(results, search_key, page)
        
        response = [
            f"📚 **Found {total} results for \"{query}\"**",
            f"Rᴇǫᴜᴇsᴛᴇᴅ Bʏ ☞ {callback_query.from_user.mention}",
            f"🔍 Showing results from Library Genesis"
        ]

        await callback_query.message.edit(
            "\n".join(response),
            reply_markup=buttons,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Pagination error: {e}")
        await callback_query.answer("Error handling pagination!")

@Client.on_callback_query(filters.regex(r"^lgdl_"))
async def handle_download_callback(client, callback_query):
    """Handle download callback queries"""
    user_id = callback_query.from_user.id
    data = callback_query.data.split('_')  # ["lgdl", "<search_key>", "<idx>"]
    search_key = data[1]
    index = int(data[2])
    original_msg = callback_query.message
    is_group = callback_query.message.chat.type in [
        enums.ChatType.GROUP, 
        enums.ChatType.SUPERGROUP
    ]

    # Try to answer immediately
    answered = await safe_answer_callback(callback_query, "📥 Starting download...")
    
    # Create progress message if needed
    if not answered:
        progress_msg = await client.send_message(
            chat_id=original_msg.chat.id,
            text="📥 Starting download from expired callback..."
        )
    else:
        progress_msg = None

    # Authentication check
    if AUTH_CHANNEL:
        missing = await is_subscribed(client, callback_query, AUTH_CHANNEL)
        if missing:
            username = (await client.get_me()).username
            param = f"lgdl_{search_key}_{index}"
            missing.append([InlineKeyboardButton("↻ Try Again", callback_data=param)])

            await callback_query.message.edit(
                "<b>🔐 You must join all required channels before downloading. Then press Try Again.</b>",
                reply_markup=InlineKeyboardMarkup(missing),
                parse_mode=enums.ParseMode.HTML
            )
            return
    
    # Verification check
    if VERIFY and not await check_verification(client, user_id):
        verify_url = await get_token(
            client,
            user_id,
            f"https://t.me/{temp.U_NAME}?start={callback_query.data}"
        )
        if not verify_url.startswith(("http://", "https://")):
            verify_url = "https://" + verify_url

        btns = [
            [InlineKeyboardButton("✅ Verify Now", url=verify_url)],
            [InlineKeyboardButton("📚 How to Verify", url=VERIFY_TUTORIAL)]
        ]
        await callback_query.message.edit(
            "<b>🔐 You need to verify for today before downloading.</b>",
            reply_markup=InlineKeyboardMarkup(btns),
            parse_mode=enums.ParseMode.HTML
        )
        return

    # Process download
    async with USER_LOCKS[user_id]:
        try: 
            # Create progress message if needed
            if progress_msg is None:
                if is_group:
                    progress_msg = await client.send_message(
                        chat_id=callback_query.message.chat.id,
                        text="⏳ Downloading book from server...",
                        reply_to_message_id=original_msg.id
                    )
                else:
                    progress_msg = await callback_query.message.reply("⏳ Downloading book from server...")
            
            # Validate cached results
            cached = search_cache.get(search_key)
            if not cached:
                await callback_query.answer("Session Expired!")
                await callback_query.message.edit("⚠️ Session Expired! Please search again.")
                return
            
            if datetime.now() > cached['time'] + timedelta(minutes=5):
                await callback_query.answer("Session Expired!")
                await callback_query.message.edit("⚠️ Session Expired! Please search again.")
                return

            results = cached['results']
            if index >= len(results):
                await callback_query.answer("Invalid selection!")
                return

            book_data = results[index]
            # Get the raw book object
            raw_book = book_data.get('RawBook')
            
            # Resolve download links only when needed
            try:
                await run_sync(raw_book.resolve_direct_download_link)
            except Exception as resolve_error:
                logger.warning(f"Direct link resolution failed: {resolve_error}")
                try:
                    await run_sync(raw_book.add_tor_download_link)
                except Exception as tor_error:
                    logger.warning(f"Tor link failed: {tor_error}")
            
            # Access attributes with comprehensive fallbacks
            mirrors = getattr(raw_book, 'mirrors', []) or getattr(raw_book, 'Mirrors', [])
            resolved = getattr(raw_book, 'resolved_download_link', None)
            tor_link = getattr(raw_book, 'tor_download_link', None) or getattr(raw_book, 'tor', None)
            first_mirror = mirrors[0] if mirrors else None

            direct_candidate = resolved or first_mirror or tor_link

            # Create complete book dictionary
            book = {
                'ID': book_data['ID'],
                'Title': book_data['Title'],
                'Author': book_data['Author'],
                'Publisher': book_data['Publisher'],
                'Year': book_data['Year'],
                'Language': book_data['Language'],
                'Pages': book_data['Pages'],
                'Size': book_data['Size'],
                'Extension': book_data['Extension'],
                'MD5': book_data['MD5'],
                'Mirror_1': book_data['Mirror_1'],
                'Mirror_2': book_data['Mirror_2'],
                'Mirror_3': book_data['Mirror_3'],
                'Mirror_4': book_data['Mirror_4'],
                'Direct_Download_Link': direct_candidate,
                'Tor_Download_Link': tor_link
            }
                
            download_url = book.get('Direct_Download_Link')

            if not download_url:
                try:
                    await safe_answer_callback(callback_query, "❌ No download available")
                except QueryIdInvalid:
                    logger.warning("Callback expired when answering 'no download available'")
                await progress_msg.edit("⚠️ No download link found for this book")
                return

            # File handling
            clean_title = "".join(c if c.isalnum() else "_" for c in book['Title'])
            file_ext = book.get('Extension', 'pdf')
            filename = f"{clean_title[:50]}.{file_ext}"
            temp_path = f"downloads/{filename}"
            os.makedirs("downloads", exist_ok=True)

            # Download attempt
            first_attempt_success = False
            try:
                if not is_group:  # Only edit message in private chats
                    await progress_msg.edit("⬇️ Downloading file... (0%)")
                    
                await download_libgen_file(
                    url=download_url,
                    temp_path=temp_path,
                    progress_msg=progress_msg,
                    user_id=user_id,
                    is_group=is_group,
                    file_name=filename
                )
                first_attempt_success = True
                
            except Exception as e:
                if "FILE_TOO_LARGE" in str(e):
                    # Use the error handler for consistent messaging
                    await handle_download_error(e, book, progress_msg, is_group)
                else:
                    await handle_download_error(e, book, progress_msg, is_group)

            # Upload to Telegram if download succeeded
            if first_attempt_success:
                if not is_group:
                    await progress_msg.edit("📤 Uploading to Telegram...")
                    
                sent_msg = await upload_to_telegram(
                    client=client,
                    temp_path=temp_path,
                    book=book,
                    progress_msg=progress_msg,
                    chat_id=callback_query.message.chat.id,
                    user_id=user_id,
                    is_group=is_group
                )

                await handle_auto_delete(client, sent_msg, callback_query.message.chat.id)
                await log_download(client, temp_path, book, callback_query)
                await progress_msg.delete()

            # Clean up temp file
            if os.path.exists(temp_path):
                try: 
                    os.remove(temp_path)
                except Exception as clean_err:
                    logger.warning(f"Failed to clean temp file: {clean_err}")

        except Exception as e:
            logger.error(f"Callback error: {e}", exc_info=True)
            if not answered and progress_msg:
                try:
                    await progress_msg.edit("❌ Error processing request")
                except:
                    pass
            try:
                await safe_answer_callback(callback_query, "❌ Error processing request")
            except QueryIdInvalid:
                pass