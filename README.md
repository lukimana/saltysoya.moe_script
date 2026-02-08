# Discord Image Fetch Bot

This bot connects to Discord, checks the **latest message** in a specific channel on a fixed interval, and if that message has an **image attachment**, it uploads the image to an SFTP server.

## 1. Prerequisites

- Python 3.11+ installed
- A Discord bot application and token
- Access to the target Discord server/channel
- An SFTP server with username/password

## 2. Install Dependencies

From the project folder:

```bash
python -m pip install -r requirements.txt
```

## 3. Create a Discord Bot and Invite It

1. Go to the Discord Developer Portal and create an application.
2. Add a **Bot** to the application.
3. Copy the bot token.
4. Under **Bot → Privileged Gateway Intents**, enable:
   - **Message Content Intent** (required if you want to read text; not required for attachments)
5. Under **OAuth2 → URL Generator**:
   - Scope: `bot`
   - Permissions:
     - `View Channels`
     - `Read Message History`
6. Open the generated URL and invite the bot to your server.

## 4. Configure `.env`

Fill in `.env` with your values:

```
# Discord
DISCORD_TOKEN=YOUR_TOKEN
CHANNEL_ID=YOUR_CHANNEL_ID

# SFTP
SFTP_HOST=YOUR_SFTP_HOST
SFTP_PORT=22
SFTP_USER=YOUR_USER
SFTP_PASSWORD=YOUR_PASSWORD
SFTP_KEY_PATH=
SFTP_KEY_PASSPHRASE=
SFTP_REMOTE_DIR=/path/on/server

# Rename pattern
RENAME_PATTERN=schedule

# State file
STATE_PATH=./state.json
```

Notes:
- `RENAME_PATTERN` supports placeholders:
  - `{timestamp}`, `{message_id}`, `{filename}`, `{base}`, `{ext}`, `{author_id}`, `{channel_id}`
- If `RENAME_PATTERN` has no extension, the bot will append the original extension automatically.

## 5. Run the Bot

```bash
python bot.py
```

You should see logs like:

```
[2026-02-08 22:31:06Z] Logged in as YourBot#1234
[2026-02-08 22:31:06Z] Check: starting
```

## 6. How It Works (Current Logic)

- Every minute, the bot fetches **only the latest message** in `CHANNEL_ID`.
- If that message is **newer** than the last processed message:
  - If it contains an image attachment, the image is uploaded to SFTP.
  - If not, it just updates the `state.json` with the latest message ID.

## 7. Common Issues

### `Missing required env var: DISCORD_TOKEN`
- The `.env` file is not being loaded or is missing the value.

### SFTP connection hangs
- Verify the host, port, username, and password.
- Ensure the SSH service is reachable.
- The bot currently uses password auth only (no key or agent).

### Bot not in member list
- You must invite it using the OAuth2 URL with **bot** scope.

## 8. Change Interval

In `bot.py`, the loop interval is:

```python
@tasks.loop(minutes=1)
```

Change `minutes=1` to a different value if needed.
