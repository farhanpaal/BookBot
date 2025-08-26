import asyncio
import logging
import aiohttp
import traceback
from info import PING_INTERVAL,URL

# Use the module's logger. Assumes your main app has already configured logging.
logger = logging.getLogger(__name__)

async def ping_server():
    """Continuously pings the server to prevent the instance from idling."""
    logger.info("Starting server ping service...")  # Log only when starting
    while True:
        await asyncio.sleep(PING_INTERVAL)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(URL) as resp:
                    if resp.status != 200:  # Only log if status is not OK
                        logger.warning(f"Unusual ping response: {resp.status}")
        except Exception as e:
            logger.error(f"Error pinging server: {e}")