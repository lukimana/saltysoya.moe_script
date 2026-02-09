# Discord bot to fetch latest image from a channel hourly and upload to SFTP
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import asyncssh
import discord
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

STATE_PATH = Path(os.getenv("STATE_PATH", "./state.json"))

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

SFTP_HOST = os.getenv("SFTP_HOST")
SFTP_PORT = int(os.getenv("SFTP_PORT", "22"))
SFTP_USER = os.getenv("SFTP_USER")
SFTP_PASSWORD = os.getenv("SFTP_PASSWORD")
SFTP_KEY_PATH = os.getenv("SFTP_KEY_PATH")
SFTP_KEY_PASSPHRASE = os.getenv("SFTP_KEY_PASSPHRASE")
SFTP_REMOTE_DIR = os.getenv("SFTP_REMOTE_DIR", ".")

RENAME_PATTERN = os.getenv("RENAME_PATTERN", "{timestamp}_{message_id}_{filename}")
RETRY_DELAY_SECONDS = int(os.getenv("RETRY_DELAY_SECONDS", "600"))
UPLOAD_TIMEOUT_SECONDS = int(os.getenv("UPLOAD_TIMEOUT_SECONDS", "20"))

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"[{ts}] {msg}")

def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def require_env(name, value):
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")

def get_retry_count(state, msg_id: int) -> int:
    retry_counts = state.get("retry_counts", {})
    return int(retry_counts.get(str(msg_id), 0))

def set_retry_count(state, msg_id: int, count: int):
    retry_counts = state.get("retry_counts", {})
    if count <= 0:
        retry_counts.pop(str(msg_id), None)
    else:
        retry_counts[str(msg_id)] = count
    state["retry_counts"] = retry_counts

def is_image_attachment(att: discord.Attachment) -> bool:
    ct = att.content_type or ""
    ext = os.path.splitext(att.filename)[1].lower()
    return ct.startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}

async def upload_bytes_sftp(data: bytes, remote_name: str):
    log(f"SFTP: connecting to {SFTP_HOST}:{SFTP_PORT} as {SFTP_USER}")
    async with asyncssh.connect(
        SFTP_HOST,
        port=SFTP_PORT,
        username=SFTP_USER,
        password=SFTP_PASSWORD,
        client_keys=None,
        agent_path=None,
        known_hosts=None,
        connect_timeout=10,
        passphrase=SFTP_KEY_PASSPHRASE,
    ) as conn:
        async with conn.start_sftp_client() as sftp:
            remote_path = f"{SFTP_REMOTE_DIR.rstrip('/')}/{remote_name}"
            log(f"SFTP: uploading to {remote_path}")
            async with sftp.open(remote_path, "wb") as f:
                await f.write(data)
            log("SFTP: upload complete")

async def try_upload_once(data: bytes, new_name: str) -> bool:
    try:
        await asyncio.wait_for(upload_bytes_sftp(data, new_name), timeout=UPLOAD_TIMEOUT_SECONDS)
        return True
    except asyncio.TimeoutError:
        log("SFTP: timeout")
    except Exception as e:
        log(f"SFTP: error {e}")
    return False

async def retry_upload_after_delay(data: bytes, new_name: str, msg_id: int, filename: str):
    log(f"Retry: scheduled in {RETRY_DELAY_SECONDS} seconds for message_id={msg_id}")
    await asyncio.sleep(RETRY_DELAY_SECONDS)
    ok = await try_upload_once(data, new_name)
    if not ok:
        state = load_state()
        current_count = get_retry_count(state, msg_id) + 1
        set_retry_count(state, msg_id, current_count)
        save_state(state)
        log(f"Retry: failed for message_id={msg_id} retry_count={current_count}")
        if current_count < 3:
            asyncio.create_task(retry_upload_after_delay(data, new_name, msg_id, filename))
        else:
            state["last_message_id"] = str(msg_id)
            set_retry_count(state, msg_id, 0)
            save_state(state)
            log(f"Retry: giving up after 3 attempts, skipping message_id={msg_id}")
        return
    state = load_state()
    current_last = int(state.get("last_message_id", "0"))
    if msg_id > current_last:
        state["last_message_id"] = str(msg_id)
    set_retry_count(state, msg_id, 0)
    save_state(state)
    log(f"Retry: state saved last_message_id={msg_id}")
    log(f"Retry: uploaded {filename} as {new_name}")


intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    log(f"Logged in as {client.user}")
    await check_channel()
    check_channel.start()


@tasks.loop(hours=1)
async def check_channel():
    log("Check: starting")
    state = load_state()
    last_id = int(state.get("last_message_id", "0"))
    log(f"Check: last_message_id={last_id}")

    channel = await client.fetch_channel(int(CHANNEL_ID))
    if channel is None:
        log("Check: channel not found. Check CHANNEL_ID and bot permissions.")
        return
    log(f"Check: channel found ({channel.id}) type={type(channel).__name__}")

    messages = [m async for m in channel.history(limit=1, oldest_first=False)]
    if not messages:
        log("Check: no recent messages")
        return

    msg = messages[0]
    log(
        "Check: latest message "
        f"id={msg.id} author={msg.author.id} created_at={msg.created_at.isoformat()} "
        f"attachments={len(msg.attachments)}"
    )

    if msg.id <= last_id:
        log("Check: latest message is not newer than last_message_id")
        return

    if not msg.attachments:
        log("Check: latest message has no attachments")
        state["last_message_id"] = str(msg.id)
        save_state(state)
        log(f"Check: state saved last_message_id={msg.id}")
        return

    att = None
    for a in msg.attachments:
        if is_image_attachment(a):
            att = a
            break

    if not att:
        log("Check: latest message has no image attachments")
        state["last_message_id"] = str(msg.id)
        save_state(state)
        log(f"Check: state saved last_message_id={msg.id}")
        return

    data = await att.read()
    log(f"Check: downloaded {len(data)} bytes")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base, ext = os.path.splitext(att.filename)
    new_name = RENAME_PATTERN.format(
        timestamp=ts,
        message_id=msg.id,
        filename=att.filename,
        base=base,
        ext=ext,
        author_id=msg.author.id,
        channel_id=msg.channel.id,
    )
    if os.path.splitext(new_name)[1] == "":
        new_name = f"{new_name}{ext}"
    log(f"Check: renaming to {new_name}")

    ok = await try_upload_once(data, new_name)
    if ok:
        state["last_message_id"] = str(msg.id)
        set_retry_count(state, msg.id, 0)
        save_state(state)
        log(f"Check: state saved last_message_id={msg.id}")
        log(f"Check: uploaded {att.filename} as {new_name}")
        return

    state = load_state()
    current_count = get_retry_count(state, msg.id) + 1
    set_retry_count(state, msg.id, current_count)
    save_state(state)
    log(f"Check: upload failed retry_count={current_count}")
    if current_count < 3:
        log("Check: scheduling retry")
        asyncio.create_task(retry_upload_after_delay(data, new_name, msg.id, att.filename))
        return

    state["last_message_id"] = str(msg.id)
    set_retry_count(state, msg.id, 0)
    save_state(state)
    log(f"Check: giving up after 3 attempts, skipping message_id={msg.id}")


async def main():
    require_env("DISCORD_TOKEN", DISCORD_TOKEN)
    require_env("CHANNEL_ID", CHANNEL_ID)
    require_env("SFTP_HOST", SFTP_HOST)
    require_env("SFTP_USER", SFTP_USER)
    if not (SFTP_PASSWORD or SFTP_KEY_PATH):
        raise RuntimeError("Provide SFTP_PASSWORD or SFTP_KEY_PATH")

    await client.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
