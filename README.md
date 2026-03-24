# Discord Schedule + YouTube Sync Bot

This bot connects to Discord and runs hourly checks for two channels:
- An image channel (`CHANNEL_ID`): uploads the newest image attachment to SFTP.
- A YouTube channel (`YOUTUBE_CHANNEL_ID`): extracts the newest YouTube link and uploads `latest-video.json` to SFTP.

## 1. Prerequisites

- Python 3.8+ installed (required by `discord.py` 2.x)
- A Discord bot application and token
- Access to the target Discord server/channels
- An SFTP server with username/password (or SSH key)

## 2. Install Dependencies

From the project folder:

```bash
python -m pip install -r requirements.txt
```

## 3. Create a Discord Bot and Invite It

1. Go to the Discord Developer Portal and create an application.
2. Add a **Bot** to the application.
3. Copy the bot token.
4. Under **Bot -> Privileged Gateway Intents**, enable:
   - **Message Content Intent** (needed for YouTube URL parsing from message text)
5. Under **OAuth2 -> URL Generator**:
   - Scope: `bot`
   - Permissions:
     - `View Channels`
     - `Read Message History`
6. Open the generated URL and invite the bot to your server.

## 4. Configure Environment

Use `.env.example` as template and create `.env` in the same folder as `bot.py`.

```bash
cp .env.example .env
```

Required variables in `.env`:

```env
# Discord
DISCORD_TOKEN=YOUR_TOKEN
CHANNEL_ID=YOUR_IMAGE_CHANNEL_ID
YOUTUBE_CHANNEL_ID=YOUR_YOUTUBE_LINK_CHANNEL_ID

# SFTP
SFTP_HOST=YOUR_SFTP_HOST
SFTP_PORT=22
SFTP_USER=YOUR_USER
SFTP_PASSWORD=YOUR_PASSWORD
SFTP_KEY_PATH=
SFTP_KEY_PASSPHRASE=
SFTP_REMOTE_DIR=/var/www/virtual/brikez/html/saltysoya.moe/schedule
SFTP_YOUTUBE_REMOTE_DIR=/var/www/virtual/brikez/html/saltysoya.moe/youtube

# Filenames / naming
RENAME_PATTERN=schedule
YOUTUBE_JSON_FILENAME=latest-video.json
YOUTUBE_TITLE=Latest YouTube Video

# Retry / timeout
RETRY_DELAY_SECONDS=600
UPLOAD_TIMEOUT_SECONDS=20

# State file
STATE_PATH=./state.json
```

Notes:
- `RENAME_PATTERN` supports placeholders:
  - `{timestamp}`, `{message_id}`, `{filename}`, `{base}`, `{ext}`, `{author_id}`, `{channel_id}`
- If `RENAME_PATTERN` has no extension, the original extension is appended.

## 5. Run the Bot

```bash
python bot.py
```

## 6. Current Logic

- Hourly image flow:
  - Scans recent messages in `CHANNEL_ID`.
  - Finds the first new message (newer than `last_message_id`) with an image attachment.
  - Uploads image to `SFTP_REMOTE_DIR`.
  - Stores progress in `state.json` under `last_message_id`.
  - Retries failed uploads up to 3 times.

- Hourly YouTube flow:
  - Scans recent messages in `YOUTUBE_CHANNEL_ID`.
  - Finds the first new message (newer than `youtube_last_message_id`) containing a YouTube URL.
  - Uploads JSON to `SFTP_YOUTUBE_REMOTE_DIR/YOUTUBE_JSON_FILENAME`:
    - `{ "url": "<youtube-url>", "title": "Latest YouTube Video" }`
  - Stores progress in `state.json` under `youtube_last_message_id`.

## 7. Common Issues

### `Missing required env var: ...`
- `.env` is not loaded, missing, or has empty values.
- All YouTube vars are required now:
  - `YOUTUBE_CHANNEL_ID`
  - `SFTP_YOUTUBE_REMOTE_DIR`
  - `YOUTUBE_JSON_FILENAME`
  - `YOUTUBE_TITLE`

### Supervisor shows `FATAL Exited too quickly`
- Usually caused by startup exception (missing env var or bad credentials).
- Check logs:

```bash
tail -n 80 /home/brikez/log/discord-bot.err.log
tail -n 80 /home/brikez/log/discord-bot.out.log
```

### SFTP connection hangs/fails
- Verify host/port/user/password or key auth.
- Ensure SSH service is reachable.

## 8. Change Interval

In `bot.py`, the loop interval is:

```python
@tasks.loop(hours=1)
```

Adjust as needed.

## 9. Run with supervisord (CentOS)

Example `/etc/supervisord.d/discord-bot.ini`:

```ini
[program:discord-bot]
command=/usr/bin/python3 /path/to/saltysoya.moe_script/bot.py
directory=/path/to/saltysoya.moe_script
autostart=true
autorestart=true
stopsignal=TERM
stdout_logfile=/home/brikez/log/discord-bot.out.log
stderr_logfile=/home/brikez/log/discord-bot.err.log
```

Reload and check status:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl status
```
