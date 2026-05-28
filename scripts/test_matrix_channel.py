#!/usr/bin/env python3
"""Interactive Matrix DM chat using a named alert channel config.

Usage:
    python scripts/test_matrix_channel.py --channel <name> [--user <target>]

    --channel   Channel config name (first match by name in the datastore)
    --user      Target Matrix user.  Accepted forms:
                  martin              → @martin:<homeserver domain>
                  @martin             → @martin:<homeserver domain>
                  @martin:example.com → used as-is
    --db        Path to the SQLite datastore (default: config/app_data.db)
"""
import argparse
import asyncio
import curses
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_channel_config(db_path: Path, channel_name: str) -> dict:
    """Return the first channel config whose name matches channel_name."""
    if not db_path.exists():
        sys.exit(f"Datastore not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, type, name, config FROM alert_channel_configs"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        sys.exit("No channel configs found in the database.")

    for row in rows:
        if row["name"] == channel_name:
            return {
                "id": row["id"],
                "type": row["type"],
                "name": row["name"],
                "config": json.loads(row["config"]) if isinstance(row["config"], str) else row["config"],
            }

    names = [r["name"] for r in rows]
    sys.exit(f"No channel named {channel_name!r}. Available: {', '.join(names)}")


def normalize_target(target: str, homeserver: str) -> str:
    """Expand a bare username to a full Matrix ID."""
    domain = urlparse(homeserver).hostname or ""
    if not target.startswith("@"):
        target = f"@{target}"
    if ":" not in target and domain:
        target = f"{target}:{domain}"
    return target


def simplify_mxid(mxid: str, homeserver: str) -> str:
    """Return just the localpart if the server matches the homeserver, else the full ID."""
    domain = urlparse(homeserver).hostname or ""
    if mxid.startswith("@") and mxid.endswith(f":{domain}"):
        return mxid[1:mxid.index(":")]
    return mxid


# ---------------------------------------------------------------------------
# Matrix helpers
# ---------------------------------------------------------------------------

def _ts_label(ts_ms: int | None = None) -> str:
    """Return a [HH:MM:SS] label in local time."""
    if ts_ms is None:
        dt = datetime.now()
    else:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone()
    return dt.strftime("[%H:%M:%S]")


async def whoami(client, homeserver: str) -> str:
    resp = await client.get(f"{homeserver}/_matrix/client/v3/account/whoami")
    resp.raise_for_status()
    return resp.json()["user_id"]


async def get_or_create_dm_room(client, homeserver: str, sender: str, target: str) -> str:
    """Return (or create) a DM room between sender and target."""
    resp = await client.get(
        f"{homeserver}/_matrix/client/v3/user/{sender}/account_data/m.direct"
    )
    if resp.status_code == 200:
        dm_map: dict = resp.json()
        rooms = dm_map.get(target, [])
        if rooms:
            return rooms[0]

    resp = await client.post(
        f"{homeserver}/_matrix/client/v3/createRoom",
        json={"is_direct": True, "invite": [target], "preset": "trusted_private_chat"},
    )
    resp.raise_for_status()
    room_id: str = resp.json()["room_id"]

    existing_resp = await client.get(
        f"{homeserver}/_matrix/client/v3/user/{sender}/account_data/m.direct"
    )
    dm_map = existing_resp.json() if existing_resp.status_code == 200 else {}
    dm_map.setdefault(target, []).append(room_id)
    await client.put(
        f"{homeserver}/_matrix/client/v3/user/{sender}/account_data/m.direct",
        json=dm_map,
    )
    return room_id


async def initial_sync_token(client, homeserver: str) -> str:
    """Quick sync with timeout=0 to get a current batch token (skip history)."""
    resp = await client.get(
        f"{homeserver}/_matrix/client/v3/sync",
        params={"timeout": 0},
    )
    resp.raise_for_status()
    return resp.json().get("next_batch", "")


async def send_message(client, homeserver: str, room_id: str, body: str) -> str:
    txn_id = f"chat-{int(time.time() * 1000)}"
    url = f"{homeserver}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"
    resp = await client.put(url, json={"msgtype": "m.text", "body": body})
    resp.raise_for_status()
    return resp.json().get("event_id", "")


# ---------------------------------------------------------------------------
# TUI
# ---------------------------------------------------------------------------

class ChatUI:
    """Curses-based chat UI: scrolling message pane above, fixed input bar below."""

    _DIVIDER_CHAR = "─"

    def __init__(self, stdscr, title: str) -> None:
        self._scr = stdscr
        self._title = title
        self._messages: list[str] = []   # rendered lines, newest last
        self._input: list[str] = []      # chars in current input buffer
        self._msg_win: curses.window | None = None
        self._inp_win: curses.window | None = None
        self._lock = asyncio.Lock()
        self._setup()

    def _setup(self) -> None:
        curses.curs_set(1)
        curses.use_default_colors()
        self._scr.nodelay(True)
        self._scr.keypad(True)
        self._rebuild_windows()

    def _rebuild_windows(self) -> None:
        rows, cols = self._scr.getmaxyx()
        # Reserve 3 rows at bottom: divider + input + status
        msg_rows = max(1, rows - 3)
        self._msg_rows = msg_rows
        self._cols = cols

        self._msg_win = curses.newwin(msg_rows, cols, 0, 0)
        self._msg_win.scrollok(True)
        self._msg_win.idlok(True)

        # Divider line
        self._div_win = curses.newwin(1, cols, msg_rows, 0)

        # Input line
        self._inp_win = curses.newwin(1, cols, msg_rows + 1, 0)
        self._inp_win.keypad(True)
        self._inp_win.nodelay(True)

        self._redraw_messages()
        self._redraw_divider()
        self._redraw_input()

    @staticmethod
    def _wrap_message(line: str, cols: int) -> list[str]:
        """Wrap a message line to cols width, breaking on spaces.

        Continuation lines are indented to align with the body start —
        i.e. past the "[HH:MM:SS] name: " prefix.
        """
        if cols < 2:
            return [line]
        if len(line) <= cols:
            return [line]

        # Find the body start: everything after the first ": "
        colon_pos = line.find(": ")
        indent = (colon_pos + 2) if colon_pos != -1 else 0
        indent = min(indent, cols // 2)  # never use more than half the width
        indent_str = " " * indent

        def _break(text: str, width: int) -> tuple[str, str]:
            """Split text at the last space within width; fall back to hard break."""
            if len(text) <= width:
                return text, ""
            space = text.rfind(" ", 0, width + 1)
            if space > 0:
                return text[:space], text[space + 1:]
            return text[:width], text[width:]

        result: list[str] = []
        first_chunk, rest = _break(line, cols)
        result.append(first_chunk)
        while rest:
            avail = cols - indent
            chunk, rest = _break(rest, avail)
            result.append(indent_str + chunk)
        return result

    def _redraw_messages(self) -> None:
        w = self._msg_win
        w.erase()
        rows, cols = w.getmaxyx()
        # Expand all messages into wrapped display lines, then take the last `rows`
        display: list[str] = []
        for msg in self._messages:
            display.extend(self._wrap_message(msg, cols))
        visible = display[-rows:]
        for i, line in enumerate(visible):
            try:
                w.addnstr(i, 0, line, cols - 1)
            except curses.error:
                pass
        w.refresh()

    def _redraw_divider(self) -> None:
        w = self._div_win
        w.erase()
        _, cols = w.getmaxyx()
        label = f" {self._title} "
        left = (cols - len(label)) // 2
        line = self._DIVIDER_CHAR * left + label + self._DIVIDER_CHAR * (cols - left - len(label))
        try:
            w.addnstr(0, 0, line[:cols - 1], cols - 1)
        except curses.error:
            pass
        w.refresh()

    def _redraw_input(self) -> None:
        w = self._inp_win
        w.erase()
        _, cols = w.getmaxyx()
        prefix = "> "
        buf = "".join(self._input)
        # Show the tail of the buffer if it overflows
        available = cols - len(prefix) - 1
        display = buf[-available:] if len(buf) > available else buf
        try:
            w.addstr(0, 0, prefix + display)
        except curses.error:
            pass
        # Place cursor at end of input
        cursor_x = min(len(prefix) + len(display), cols - 1)
        try:
            w.move(0, cursor_x)
        except curses.error:
            pass
        w.refresh()

    async def add_message(self, line: str) -> None:
        async with self._lock:
            self._messages.append(line)
            self._redraw_messages()
            self._redraw_input()  # restore cursor to input

    async def read_input(self) -> str | None:
        """
        Non-blocking character reader. Returns a complete string when Enter is
        pressed, None if no complete input is ready yet.
        Handles backspace and window resize.
        """
        loop = asyncio.get_running_loop()
        ch = await loop.run_in_executor(None, self._inp_win.getch)
        if ch == curses.ERR:
            return None
        if ch == curses.KEY_RESIZE:
            async with self._lock:
                self._rebuild_windows()
            return None
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            async with self._lock:
                if self._input:
                    self._input.pop()
                self._redraw_input()
            return None
        if ch in (10, 13):  # Enter
            async with self._lock:
                text = "".join(self._input)
                self._input.clear()
                self._redraw_input()
            return text
        if 32 <= ch <= 126:  # printable ASCII
            async with self._lock:
                self._input.append(chr(ch))
                self._redraw_input()
        return None


# ---------------------------------------------------------------------------
# Chat tasks
# ---------------------------------------------------------------------------

async def sync_receiver(
    client,
    homeserver: str,
    room_id: str,
    sender_id: str,
    since_token: str,
    stop_event: asyncio.Event,
    ui: ChatUI,
) -> None:
    """Long-poll the sync endpoint and push messages into the UI."""
    next_batch = since_token
    while not stop_event.is_set():
        try:
            resp = await client.get(
                f"{homeserver}/_matrix/client/v3/sync",
                params={"since": next_batch, "timeout": 10_000},
            )
        except Exception as exc:
            await ui.add_message(f"{_ts_label()} [sync error: {exc}]")
            await asyncio.sleep(2)
            continue

        if resp.status_code != 200:
            await ui.add_message(f"{_ts_label()} [sync HTTP {resp.status_code}]")
            await asyncio.sleep(2)
            continue

        data = resp.json()
        next_batch = data.get("next_batch", next_batch)

        joined = data.get("rooms", {}).get("join", {})
        room_data = joined.get(room_id, {})
        events = room_data.get("timeline", {}).get("events", [])

        for ev in events:
            if ev.get("type") != "m.room.message":
                continue
            ev_sender = ev.get("sender", "")
            if ev_sender == sender_id:
                continue  # skip our own echoed messages
            content = ev.get("content", {})
            if "m.relates_to" in content:
                continue
            body = content.get("body", "")
            ts_ms = ev.get("origin_server_ts")
            label = _ts_label(ts_ms)
            name = simplify_mxid(ev_sender, homeserver)
            await ui.add_message(f"{label} {name}: {body}")


async def input_sender(
    client,
    homeserver: str,
    room_id: str,
    sender_id: str,
    stop_event: asyncio.Event,
    ui: ChatUI,
) -> None:
    """Poll the UI for input and send completed lines as Matrix messages."""
    display_name = simplify_mxid(sender_id, homeserver)
    while not stop_event.is_set():
        text = await ui.read_input()
        if text is None:
            await asyncio.sleep(0.02)
            continue
        if not text:
            continue
        if text.lower() in ("/quit", "/exit"):
            stop_event.set()
            return
        ts = _ts_label()
        try:
            await send_message(client, homeserver, room_id, text)
            await ui.add_message(f"{ts} {display_name}: {text}")
        except Exception as exc:
            await ui.add_message(f"{ts} [send error: {exc}]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(stdscr, homeserver: str, access_token: str, target: str) -> None:
    import httpx

    # Pre-connect status shown before curses takes over — we print to the
    # curses window instead since stdscr is already active here.
    status_lines: list[str] = []

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30.0,
    ) as client:
        status_lines.append(f"Connecting to {homeserver} …")
        sender = await whoami(client, homeserver)
        status_lines.append(f"Authenticated as : {sender}")
        status_lines.append(f"Target           : {target}")

        room_id = await get_or_create_dm_room(client, homeserver, sender, target)
        status_lines.append(f"DM room          : {room_id}")
        status_lines.append("Syncing …")

        since = await initial_sync_token(client, homeserver)
        status_lines.append("Ready. /quit to exit.")

        title = f"{simplify_mxid(sender, homeserver)} → {simplify_mxid(target, homeserver)}"
        ui = ChatUI(stdscr, title)

        for line in status_lines:
            await ui.add_message(line)

        stop = asyncio.Event()
        async with asyncio.TaskGroup() as tg:
            tg.create_task(sync_receiver(client, homeserver, room_id, sender, since, stop, ui))
            tg.create_task(input_sender(client, homeserver, room_id, sender, stop, ui))


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive Matrix DM via a named channel config")
    parser.add_argument("--channel", required=True, help="Channel config name")
    parser.add_argument("--user", default=None, help="Target user (bare name, @name, or full Matrix ID)")
    parser.add_argument(
        "--db",
        default="config/app_data.db",
        type=Path,
        help="Path to the SQLite datastore (default: config/app_data.db)",
    )
    args = parser.parse_args()

    cfg = load_channel_config(args.db, args.channel)
    if cfg["type"] != "matrix":
        sys.exit(f"Channel {args.channel!r} has type {cfg['type']!r}, expected 'matrix'")

    params: dict = cfg["config"]
    homeserver: str = params.get("homeserver", "").rstrip("/")
    access_token: str = params.get("access_token", "")
    if not homeserver or not access_token:
        sys.exit("Channel config is missing 'homeserver' or 'access_token'")

    if args.user is None:
        sys.exit("--user is required")

    target = normalize_target(args.user, homeserver)

    def _run(stdscr) -> None:
        asyncio.run(run(stdscr, homeserver, access_token, target))

    try:
        curses.wrapper(_run)
    except KeyboardInterrupt:
        pass
    print("Bye.")


if __name__ == "__main__":
    main()
