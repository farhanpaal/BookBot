import jinja2
from info import *
from Zahid.bot import ZahidBot
from Zahid.util.human_readable import humanbytes
from Zahid.util.file_properties import get_file_ids
from Zahid.server.exceptions import InvalidHash
import urllib.parse
import logging
import aiohttp


async def render_page(id, secure_hash, src=None):
    file = await ZahidBot.get_messages(int(LOG_CHANNEL), int(id))
    file_data = await get_file_ids(ZahidBot, int(LOG_CHANNEL), int(id))
    if file_data.unique_id[:6] != secure_hash:
        logging.debug(f"link hash: {secure_hash} - {file_data.unique_id[:6]}")
        logging.debug(f"Invalid hash for message with - ID {id}")
        raise InvalidHash

    src = urllib.parse.urljoin(
        URL,
        f"{id}/{urllib.parse.quote_plus(file_data.file_name)}?hash={secure_hash}",
    )

    tag = file_data.mime_type.split("/")[0].strip()
    file_size = humanbytes(file_data.file_size)

    if file_data.mime_type == "application/pdf":
        template_file = "Zahid/template/pdf.html"
    elif tag in ["video", "audio"]:
        template_file = "Zahid/template/req.html"
    elif file_data.mime_type in ["application/epub", "application/epub+zip"]:
        template_file = "Zahid/template/epub.html"    
    elif file_data.mime_type == "application/epub":
        template_file = "Zahid/template/epub.html"    
    else:
        template_file = "Zahid/template/dl.html"
        
        async with aiohttp.ClientSession() as s:
            async with s.get(src) as u:
                file_size = humanbytes(int(u.headers.get("Content-Length")))

    with open(template_file) as f:
        template = jinja2.Template(f.read())

    file_name = file_data.file_name.replace("_", " ")

    return template.render(
        file_name=file_name,
        file_url=src,
        file_size=file_size,
        file_unique_id=file_data.unique_id,
    )
