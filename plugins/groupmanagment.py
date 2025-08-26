from pyrogram.types import *
from pyrogram.errors import FloodWait
from pyrogram import Client, filters, enums
from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden
from pyrogram.errors.exceptions.bad_request_400 import ChatAdminRequired, UserAdminInvalid

from utils import extract_time, extract_user, admin_check, admin_filter                        
from info import *
from Script import script
from time import time
import asyncio



@Client.on_message(filters.command("gban"))
async def ban_user(_, message):
    is_admin = await admin_check(message)
    if not is_admin: return 
    user_id, user_first_name = extract_user(message)
    try: await message.chat.ban_member(user_id=user_id)
    except Exception as error: await message.reply_text(str(error))                    
    else:
        if str(user_id).lower().startswith("@"):
            await message.reply_text(f"Someone else is dusting off..! \n{user_first_name} \nIs forbidden.")                              
        else:
            await message.reply_text(f"Someone else is dusting off..! \n<a href='tg://user?id={user_id}'>{user_first_name}</a> Is forbidden")                      
            

@Client.on_message(filters.command("tban"))
async def temp_ban_user(_, message):
    is_admin = await admin_check(message)
    if not is_admin: return
    if not len(message.command) > 1: return
    user_id, user_first_name = extract_user(message)
    until_date_val = extract_time(message.command[1])
    if until_date_val is None: return await message.reply_text(text=f"Invalid time type specified. \nExpected m, h, or d, Got it: {message.command[1][-1]}")   
    try: await message.chat.ban_member(user_id=user_id, until_date=until_date_val)            
    except Exception as error: await message.reply_text(str(error))
    else:
        if str(user_id).lower().startswith("@"):
            await message.reply_text(f"Someone else is dusting off..!\n{user_first_name}\nbanned for {message.command[1]}!")
        else:
            await message.reply_text(f"Someone else is dusting off..!\n<a href='tg://user?id={user_id}'>Lavane</a>\n banned for {message.command[1]}!")
                

@Client.on_message(filters.command(["gunban", "unmute"]))
async def un_ban_user(_, message):
    is_admin = await admin_check(message)
    if not is_admin: return
    user_id, user_first_name = extract_user(message)
    try: await message.chat.unban_member(user_id=user_id)
    except Exception as error: await message.reply_text(str(error))
    else:
        if str(user_id).lower().startswith("@"):
            await message.reply_text(f"Okay, changed ... now {user_first_name} can speak freely again! 🗣️")
        else:
            await message.reply_text(f"Okay, changed ... now <a href='tg://user?id={user_id}'>{user_first_name}</a> can speak freely again! 🗣️")           
            
from pyrogram import Client, filters
from pyrogram.types import ChatPermissions

@Client.on_message(filters.command("mute"))
async def mute_user(_, message):
    # 1) Check if sender is an admin
    is_admin = await admin_check(message)
    if not is_admin:
        return

    # 2) Extract target user
    user_id, user_first_name = await extract_user(message)
    if not user_id:
        return await message.reply_text("❌ Could not find a valid user to mute.")

    # 3) Determine reason
    parts = message.command  # ["mute", "@username", "reason words..."] or ["mute", "123456", "reason..."]
    if message.reply_to_message:
        # If this was a reply, everything after "mute" is the reason
        reason_tokens = parts[1:]
    else:
        # If not a reply, expect at least: /mute <username_or_id> <reason>
        if len(parts) < 3:
            return await message.reply_text("Usage: /mute <username_or_id> <reason>")
        reason_tokens = parts[2:]
    reason = " ".join(reason_tokens).strip()
    if not reason:
        reason = "No reason provided"

    # 4) Attempt to mute (restrict) the user
    try:
        await message.chat.restrict_member(
            user_id=user_id,
            permissions=ChatPermissions()  # no send permissions = muted
        )
    except Exception as error:
        return await message.reply_text(f"❌ Failed to mute user:\n{error}")

    # 5) Send confirmation including the reason
    if message.reply_to_message or str(user_id).startswith("@"):
        # If the user was identified by username or by reply, just use their first name
        await message.reply_text(
            f"👍🏻 {user_first_name} has been muted.\nReason: {reason} 🤐"
        )
    else:
        # Otherwise, mention by numeric ID in HTML
        await message.reply_text(
            f"👍🏻 <a href='tg://user?id={user_id}'>{user_first_name}</a> has been muted.\nReason: {reason} 🤐",
            parse_mode=enums.ParseMode.HTML
        )


from pyrogram import Client, filters
from pyrogram.types import ChatPermissions

@Client.on_message(filters.command("tmute"))
async def temp_mute_user(_, message):
    # 0) Check if sender is an admin
    is_admin = await admin_check(message)
    if not is_admin:
        return

    # 1) Expect at least: /tmute <duration> <reason>
    if len(message.command) < 3:
        return await message.reply_text(
            "Usage: /tmute <duration> <reason>\n"
            "Example: /tmute 15m spamming links"
        )

    # 2) Extract the target user
    user_id, user_first_name = extract_user(message)
    if not user_id:
        return await message.reply_text("❌ Could not find a valid user to mute.")

    # 3) Parse the duration token (second element)
    duration_token = message.command[1]
    until_date_val = extract_time(duration_token)
    if until_date_val is None:
        return await message.reply_text(
            f"Invalid time type specified. Expected m, h, or d. Got: {duration_token[-1]}"
        )

    # 4) Everything after the duration is the reason
    reason_tokens = message.command[2:]
    reason = " ".join(reason_tokens).strip()
    if not reason:
        reason = "No reason provided"

    # 5) Attempt to mute the user
    try:
        await message.chat.restrict_member(
            user_id=user_id,
            permissions=ChatPermissions(),       # No permissions = fully muted
            until_date=until_date_val
        )
    except Exception as error:
        return await message.reply_text(f"❌ Failed to mute user:\n{error}")

    # 6) Build the mention string (link if possible)
    if str(user_id).startswith("@"):
        mention = user_first_name
    else:
        mention = f"<a href='tg://user?id={user_id}'>{user_first_name}</a>"

    # 7) Send confirmation including the reason
    await message.reply_text(
        f"🔇 {mention} has been muted for {duration_token}.\n"
        f"• Reason: {reason}",
        parse_mode=enums.ParseMode.HTML
    )


@Client.on_message(filters.command("pin") & filters.create(admin_filter))
async def pin(_, message: Message):
    if not message.reply_to_message: return
    await message.reply_to_message.pin()


@Client.on_message(filters.command("unpin") & filters.create(admin_filter))             
async def unpin(_, message: Message):
    if not message.reply_to_message: return
    await message.reply_to_message.unpin()



@Client.on_message(filters.command("purge") & (filters.group | filters.channel))                   
async def purge(client, message):
    if message.chat.type not in ((enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL)): return
    is_admin = await admin_check(message)
    if not is_admin: return
    status_message = await message.reply_text("...", quote=True)
    await message.delete()
    message_ids = []
    count_del_etion_s = 0
    if message.reply_to_message:
        for a_s_message_id in range(message.reply_to_message.id, message.id):
            message_ids.append(a_s_message_id)
            if len(message_ids) == "100":
                await client.delete_messages(chat_id=message.chat.id, message_ids=message_ids, revoke=True)              
                count_del_etion_s += len(message_ids)
                message_ids = []
        if len(message_ids) > 0:
            await client.delete_messages(chat_id=message.chat.id, message_ids=message_ids, revoke=True)
            count_del_etion_s += len(message_ids)
    await status_message.edit_text(f"deleted {count_del_etion_s} messages")
    await status_message.delete()
    

@Client.on_message(filters.group & filters.command('inkick'))
async def inkick(client, message):
    user = await client.get_chat_member(message.chat.id, message.from_user.id)
    if user.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):      
        note = await message.reply_text(script.CREATOR_REQUIRED)
        await asyncio.sleep(3)
        await note.delete()
        return await message.delete()
    if len(message.command) > 1:
        input_str = message.command
        sent_message = await message.reply_text(script.START_KICK)
        await asyncio.sleep(2)
        await message.delete()
        count = 0
        for member in client.get_chat_members(message.chat.id):
            if member.user.status in input_str and not member.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
                try:
                    client.ban_chat_member(message.chat.id, member.user.id, int(time() + 45))
                    count += 1
                except (ChatAdminRequired, UserAdminInvalid):
                    await sent_message.edit(script.ADMIN_REQUIRED)
                    await client.leave_chat(message.chat.id)
                    break
                except FloodWait as e:
                    await asyncio.sleep(e.value)
        try:
            await sent_message.edit(script.KICKED.format(count))
        except ChatWriteForbidden: pass
    else:
        await message.reply_text(script.INPUT_REQUIRED)
  

@Client.on_message(filters.group & filters.command('dkick'))
async def dkick(client, message):
    user = await client.get_chat_member(message.chat.id, message.from_user.id)
    if user.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):      
        note = await message.reply_text(script.CREATOR_REQUIRED)
        await asyncio.sleep(3)
        await note.delete()
        return await message.delete()
    sent_message = await message.reply_text(script.START_KICK)
    await message.delete()
    count = 0
    for member in client.get_chat_members(message.chat.id):
        if member.user.is_deleted and not member.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
            try:
                await client.ban_chat_member(message.chat.id, member.user.id, int(time() + 45))
                count += 1
            except (ChatAdminRequired, UserAdminInvalid):
                await sent_message.edit(script.ADMIN_REQUIRED)
                await client.leave_chat(message.chat.id)
                break
            except FloodWait as e:
                await asyncio.sleep(e.value)
    try:
        await sent_message.edit(script.DKICK.format(count))
    except ChatWriteForbidden: pass
  
  
@Client.on_message((filters.channel | filters.group) & filters.command('instatus'))
async def instatus(client, message):
    user = await client.get_chat_member(message.chat.id, message.from_user.id)
    if user.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER, ADMINS):
        note = await message.reply("you are not administrator in this chat")
        await asyncio.sleep(3)
        await message.delete()
        return await note.delete()
    sent_message = await message.reply_text("🔁 Processing.....")
    recently = 0
    within_week = 0
    within_month = 0
    long_time_ago = 0
    deleted_acc = 0
    uncached = 0
    bot = 0
    for member in client.get_chat_members(message.chat.id):
        if member.user.is_deleted: deleted_acc += 1
        elif member.user.is_bot: bot += 1
        elif member.user.status == enums.UserStatus.RECENTLY: recently += 1
        elif member.user.status == enums.UserStatus.LAST_WEEK: within_week += 1
        elif member.user.status == enums.UserStatus.LAST_MONTH: within_month += 1
        elif member.user.status == enums.UserStatus.LONG_AGO: long_time_ago += 1
        else: uncached += 1
    if message.chat.type == enums.ChatType.CHANNEL:
        await sent_message.edit(f"{message.chat.title}\nChat Member Status\n\nRecently - {recently}\nWithin Week - {within_week}\nWithin Month - {within_month}\nLong Time Ago - {long_time_ago}\n\nDeleted Account - {deleted_acc}\nBot - {bot}\nUnCached - {uncached}")            
    elif message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await sent_message.edit(f"{message.chat.title}\nChat Member Status\n\nRecently - {recently}\nWithin Week - {within_week}\nWithin Month - {within_month}\nLong Time Ago - {long_time_ago}\n\nDeleted Account - {deleted_acc}\nBot - {bot}\nUnCached - {uncached}")
        
            
  