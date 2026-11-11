#!/usr/bin/env python3
"""Send coach output (recaps, reports, plans, short messages) to the athlete's Telegram chat.

Uses the Telegram Bot API (https://core.telegram.org/bots/api) with the standard library only.

Bot token (never printed): $TELEGRAM_BOT_TOKEN, else ~/.config/telegram/bot-token.
Chat id:                   $TELEGRAM_CHAT_ID,   else ~/.config/telegram/chat-id.
Create the bot with @BotFather, send it one message, then `python scripts/telegram.py chat-id` prints your id.

Usage:
    python scripts/telegram.py status                         # check the token and chat
    python scripts/telegram.py chat-id                        # chat ids that recently wrote to the bot
    python scripts/telegram.py text "Easy 40' today"          # plain message (or "-" to read stdin)
    python scripts/telegram.py send FILE [--caption "..."]    # .html/.pdf/... → document, .png/.jpg → photo,
                                                              # .md/.txt → message text (use --as-file to attach)
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

BASE_URL = "https://api.telegram.org"
CONFIG_DIR = Path("~/.config/telegram").expanduser()
TOKEN_FILE = CONFIG_DIR / "bot-token"
CHAT_FILE = CONFIG_DIR / "chat-id"
MAX_TEXT = 4096          # Telegram message limit (characters)
MAX_CAPTION = 1024
PHOTO_EXT = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_EXT = {".md", ".txt"}


class TelegramError(RuntimeError):
    """Missing/rejected token or failed request."""


def _read(env: str, path: Path) -> str | None:
    value = os.environ.get(env, "").strip()
    if value:
        return value
    if path.exists():
        return path.read_text(encoding="utf-8").strip() or None
    return None


def configured() -> bool:
    """True when both a bot token and a chat id are available (not validated)."""
    return _read("TELEGRAM_BOT_TOKEN", TOKEN_FILE) is not None and _read("TELEGRAM_CHAT_ID", CHAT_FILE) is not None


def chat_id() -> str:
    cid = _read("TELEGRAM_CHAT_ID", CHAT_FILE)
    if not cid:
        raise TelegramError(f"no chat id. Run `scripts/telegram.py chat-id` and save it to {CHAT_FILE} "
                            "(or set TELEGRAM_CHAT_ID).")
    return cid


def _call(method: str, fields: dict[str, Any] | None = None, file_field: str | None = None,
          file_path: Path | None = None) -> Any:
    token = _read("TELEGRAM_BOT_TOKEN", TOKEN_FILE)
    if not token:
        raise TelegramError(f"no bot token. Create a bot with @BotFather and save the token to {TOKEN_FILE} "
                            "(or set TELEGRAM_BOT_TOKEN).")
    url = f"{BASE_URL}/bot{token}/{method}"
    fields = {k: v for k, v in (fields or {}).items() if v is not None}
    if file_path is not None:
        boundary = uuid.uuid4().hex
        parts: list[bytes] = []
        for k, v in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
                     f'filename="{file_path.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode())
        parts.append(file_path.read_bytes())
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        data = b"".join(parts)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    else:
        data = json.dumps(fields).encode()
        headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read())
        except (urllib.error.URLError, ConnectionError) as e:
            if isinstance(e, urllib.error.HTTPError):
                raise
            # uploads to api.telegram.org get the odd connection reset: retry once
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            desc = json.loads(e.read()).get("description", "")
        except Exception:  # noqa: BLE001
            desc = ""
        raise TelegramError(f"{method}: HTTP {e.code} {desc}".strip()) from None
    except (urllib.error.URLError, ConnectionError) as e:
        raise TelegramError(f"{method}: {getattr(e, 'reason', e)}") from None
    if not payload.get("ok"):
        raise TelegramError(f"{method}: {payload.get('description', 'failed')}")
    return payload["result"]


def _chunks(text: str, limit: int = MAX_TEXT) -> list[str]:
    """Split on line boundaries so each piece fits one Telegram message."""
    out: list[str] = []
    buf = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if buf:
                out.append(buf)
                buf = ""
            out.append(line[:limit])
            line = line[limit:]
        if len(buf) + len(line) > limit:
            out.append(buf)
            buf = ""
        buf += line
    if buf.strip():
        out.append(buf)
    return out


def send_text(text: str) -> int:
    """Send plain text (no parse mode: markdown from reports is shown as-is). Returns the number of messages."""
    pieces = _chunks(text)
    for piece in pieces:
        _call("sendMessage", {"chat_id": chat_id(), "text": piece, "disable_web_page_preview": True})
    return len(pieces)


def send_file(path: Path, caption: str | None = None, as_file: bool = False) -> str:
    """Send a file the right way for its type. Returns what was sent ("photo", "document" or "text")."""
    if not path.is_file():
        raise TelegramError(f"no such file: {path}")
    ext = path.suffix.lower()
    if ext in TEXT_EXT and not as_file:
        body = path.read_text(encoding="utf-8")
        send_text(f"{caption}\n\n{body}" if caption else body)
        return "text"
    cap = caption[:MAX_CAPTION] if caption else None
    if ext in PHOTO_EXT and path.stat().st_size <= 10 * 1024 * 1024:
        _call("sendPhoto", {"chat_id": chat_id(), "caption": cap}, "photo", path)
        return "photo"
    _call("sendDocument", {"chat_id": chat_id(), "caption": cap}, "document", path)
    return "document"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="check the bot token and chat id")
    sub.add_parser("chat-id", help="list chats that recently messaged the bot")
    t = sub.add_parser("text", help="send a plain message")
    t.add_argument("message", help='text, or "-" to read stdin')
    s = sub.add_parser("send", help="send a file (recap HTML, report, image...)")
    s.add_argument("file", type=Path)
    s.add_argument("--caption")
    s.add_argument("--as-file", action="store_true", help="attach .md/.txt as a document instead of text")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "status":
            me = _call("getMe")
            chat = _call("getChat", {"chat_id": chat_id()})
            who = chat.get("username") or chat.get("first_name") or chat.get("title") or chat["id"]
            print(f"Telegram OK — bot @{me['username']} → chat {who}")
        elif args.cmd == "chat-id":
            seen = {}
            for upd in _call("getUpdates"):
                msg = upd.get("message") or upd.get("channel_post") or {}
                c = msg.get("chat")
                if c:
                    seen[c["id"]] = c.get("username") or c.get("first_name") or c.get("title") or ""
            if not seen:
                print("no recent messages: send any message to the bot in Telegram, then run this again")
            for cid, name in seen.items():
                print(f"{cid}\t{name}")
        elif args.cmd == "text":
            msg = sys.stdin.read() if args.message == "-" else args.message
            n = send_text(msg)
            print(f"sent {n} message(s)")
        elif args.cmd == "send":
            kind = send_file(args.file, args.caption, args.as_file)
            print(f"sent {args.file.name} as {kind}")
    except TelegramError as e:
        print(f"telegram: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
