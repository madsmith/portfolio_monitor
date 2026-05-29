#!/usr/bin/env python3
"""Interactive OpenClaw Gateway WebSocket test using a configured delivery channel.

Usage:
    python scripts/test_openclaw_ws_channel.py --config-id <id> [options]
    python scripts/test_openclaw_ws_channel.py --channel <name> --agent <id> [options]

    --config-id    Delivery channel ID (alert_channels.id) — resolves connection
                   and user params from the configured delivery channel
    --channel      Channel config name (alert_channel_configs) — use when no
                   delivery channel is configured; requires --agent
    --agent        Agent ID (overrides delivery channel agentId)
    --session-key  Session key (short suffix or full "agent:…" key)
    --extra-prompt Additional system prompt injected alongside the message
    --thinking     Thinking level: off / low / medium / high
    --bootstrap    Bootstrap context mode: lightweight / full
    --run-kind     Bootstrap run kind: cron / heartbeat
    --deliver      Push agent reply outbound (default: false)
    --db           Path to SQLite datastore (default: config/app_data.db)
"""
from __future__ import annotations

import argparse
import asyncio
import curses
import json
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Allow importing from src/
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from portfolio_monitor.service.alerts.delivery.openclaw_websocket import OpenClawWsDelivery


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def load_channel_config(db_path: Path, channel_name: str) -> dict:
    """Return the alert_channel_configs row whose name matches channel_name."""
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
            cfg = row["config"]
            return {
                "id": row["id"],
                "type": row["type"],
                "name": row["name"],
                "config": json.loads(cfg) if isinstance(cfg, str) else cfg,
            }

    names = [r["name"] for r in rows]
    sys.exit(f"No channel named {channel_name!r}. Available: {', '.join(names)}")


def load_delivery_channel_by_id(db_path: Path, config_id: str) -> tuple[dict, dict]:
    """Load an alert_channels row by id and resolve its alert_channel_configs entry.

    Returns (channel_cfg, user_params) where channel_cfg is the alert_channel_configs
    row and user_params is parsed from the delivery channel target.
    """
    if not db_path.exists():
        sys.exit(f"Datastore not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, owner, channel_config_id, target, mode FROM alert_channels WHERE id = ?",
            (config_id,),
        ).fetchone()
        if row is None:
            sys.exit(f"No delivery channel found with id {config_id!r}")
        cfg_row = conn.execute(
            "SELECT id, type, name, config FROM alert_channel_configs WHERE id = ?",
            (row["channel_config_id"],),
        ).fetchone()
    finally:
        conn.close()
    if cfg_row is None:
        sys.exit(f"Delivery channel {config_id!r} references missing channel config {row['channel_config_id']!r}")
    raw_cfg = cfg_row["config"]
    channel_cfg = {
        "id": cfg_row["id"],
        "type": cfg_row["type"],
        "name": cfg_row["name"],
        "config": json.loads(raw_cfg) if isinstance(raw_cfg, str) else raw_cfg,
    }
    return channel_cfg, parse_target(row["target"])


def parse_target(target: str) -> dict:
    """Parse a delivery channel target — plain string or JSON object."""
    if target.startswith("{"):
        try:
            return json.loads(target)
        except json.JSONDecodeError:
            pass
    return {"agentId": target}


# ---------------------------------------------------------------------------
# Frame builder
# ---------------------------------------------------------------------------

def build_agent_frame(message: str, user: dict) -> dict:
    """Build an agent method frame from user-level params and a free-form message."""
    agent_id: str = user.get("agentId", "")
    idempotency_key = str(uuid.uuid4())

    params: dict = {
        "agentId": agent_id,
        "message": message,
        "idempotencyKey": idempotency_key,
        "label": f"Portfolio Alerts",
        "inputProvenance": {"kind": "external_user", "sourceChannel": "portfolio-monitor"},
        "deliver": bool(user.get("deliver", False)),
        "bootstrapContextMode": user.get("bootstrapContextMode", "lightweight"),
        "bootstrapContextRunKind": user.get("bootstrapContextRunKind", "cron"),
    }

    if channel := user.get("channel"):
        params["channel"] = channel
    if timeout := user.get("timeout"):
        params["timeout"] = int(timeout)

    session_key: str = user.get("sessionKey", "")
    if session_key:
        params["sessionKey"] = (
            session_key if session_key.startswith("agent:")
            else f"agent:{agent_id}:{session_key}"
        )

    if extra_prompt := user.get("extraPrompt"):
        params["extraSystemPrompt"] = extra_prompt
    if thinking := user.get("thinking"):
        params["thinking"] = thinking

    return {
        "type": "req",
        "id": f"msg-{idempotency_key[:8]}",
        "method": "agent",
        "params": params,
    }


# ---------------------------------------------------------------------------
# TUI
# ---------------------------------------------------------------------------

class ChatUI:
    """Curses-based TUI: scrolling message pane above, fixed input bar below."""

    _DIVIDER_CHAR = "─"

    def __init__(self, stdscr, title: str) -> None:
        self._scr = stdscr
        self._title = title
        self._messages: list[str] = []
        self._input: list[str] = []
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
        msg_rows = max(1, rows - 3)
        self._msg_rows = msg_rows
        self._cols = cols

        self._msg_win = curses.newwin(msg_rows, cols, 0, 0)
        self._msg_win.scrollok(True)
        self._msg_win.idlok(True)

        self._div_win = curses.newwin(1, cols, msg_rows, 0)
        self._inp_win = curses.newwin(1, cols, msg_rows + 1, 0)
        self._inp_win.keypad(True)
        self._inp_win.nodelay(True)

        self._redraw_messages()
        self._redraw_divider()
        self._redraw_input()

    @staticmethod
    def _wrap(line: str, cols: int) -> list[str]:
        # Indent continuation lines to align under the opening { if present,
        # otherwise fall back to just past the [HH:MM:SS] prefix (11 chars).
        brace = line.find("{")
        indent = brace if brace != -1 else 11
        indent = min(indent, cols // 2)
        indent_str = " " * indent

        def _break(text: str, width: int) -> tuple[str, str]:
            if len(text) <= width:
                return text, ""
            sp = text.rfind(" ", 0, width + 1)
            return (text[:sp], text[sp + 1:]) if sp > 0 else (text[:width], text[width:])

        if cols < 2 or len(line) <= cols:
            return [line]

        result: list[str] = []
        first, rest = _break(line, cols)
        result.append(first)
        while rest:
            chunk, rest = _break(rest, cols - indent)
            result.append(indent_str + chunk)
        return result

    def _redraw_messages(self) -> None:
        w = self._msg_win
        w.erase()
        rows, cols = w.getmaxyx()
        display: list[str] = []
        for msg in self._messages:
            display.extend(self._wrap(msg, cols))
        for i, line in enumerate(display[-rows:]):
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
        available = cols - len(prefix) - 1
        display = buf[-available:] if len(buf) > available else buf
        try:
            w.addstr(0, 0, prefix + display)
        except curses.error:
            pass
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
            self._redraw_input()

    async def read_input(self) -> str | None:
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
        if ch in (10, 13):
            async with self._lock:
                text = "".join(self._input)
                self._input.clear()
                self._redraw_input()
            return text
        if 32 <= ch <= 126:
            async with self._lock:
                self._input.append(chr(ch))
                self._redraw_input()
        return None


# ---------------------------------------------------------------------------
# Async tasks
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now().strftime("[%H:%M:%S]")


def _trunc(s: str, max_len: int = 380) -> str:
    """Middle-truncate a string: keep head and tail with … in between."""
    if len(s) <= max_len:
        return s
    head = max_len * 3 // 4
    tail = max_len - head - 1
    return f"{s[:head]}…{s[-tail:]}"


async def gateway_reader(delivery: OpenClawWsDelivery, stop: asyncio.Event, ui: ChatUI) -> None:
    """Drain incoming frames from the gateway and display them in the TUI."""
    import websockets

    ws = delivery._ws
    try:
        async for raw in ws:
            try:
                msg: dict = json.loads(raw)
            except json.JSONDecodeError:
                await ui.add_message(f"{_ts()} [bad frame: {raw}]")
                continue

            msg_type = msg.get("type")
            if msg_type == "res":
                req_id = msg.get("id", "?")
                if msg.get("ok"):
                    result = msg.get("result", {})
                    run_id = result.get("runId", "")
                    suffix = f"  runId={run_id}" if run_id else ""
                    await ui.add_message(f"{_ts()} [ok] {req_id}{suffix}")
                else:
                    error = msg.get("error", "unknown")
                    detail = msg.get("message", "")
                    await ui.add_message(f"{_ts()} [error] {req_id}: {error}" + (f" — {detail}" if detail else ""))
            elif msg_type != "event":

                await ui.add_message(f"{_ts()} [frame] {_trunc(json.dumps(msg))}")

    except websockets.ConnectionClosed:
        await ui.add_message(f"{_ts()} [connection closed]")
        stop.set()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await ui.add_message(f"{_ts()} [reader error: {exc}]")
        stop.set()


async def input_sender(delivery: OpenClawWsDelivery, user: dict, stop: asyncio.Event, ui: ChatUI) -> None:
    """Poll the UI for input and send each line as a gateway agent frame."""
    while not stop.is_set():
        text = await ui.read_input()
        if text is None:
            await asyncio.sleep(0.02)
            continue
        if not text:
            continue
        if text.lower() in ("/quit", "/exit"):
            stop.set()
            return
        frame = build_agent_frame(text, user)
        req_id = frame["id"]
        agent_id = frame["params"]["agentId"]
        ts = _ts()
        try:
            await delivery._ws.send(json.dumps(frame))
            await ui.add_message(f"{ts} → [{req_id}] agent:{agent_id}  {text}")
        except Exception as exc:
            await ui.add_message(f"{ts} [send error: {exc}]")
            stop.set()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(stdscr, channel_params: dict, user: dict) -> None:
    delivery = OpenClawWsDelivery.from_channel_params(channel_params)

    status_lines: list[str] = [f"Connecting to ws://{channel_params['host']}:{channel_params['port']} …"]
    await delivery.connect()
    status_lines.append("Handshake OK")
    status_lines.append(f"Agent ID : {user.get('agentId', '(none)')}")
    if sk := user.get("sessionKey"):
        status_lines.append(f"Session  : {sk}")
    status_lines.append("Ready. /quit to exit.")

    # The delivery class starts an internal reader for error logging; cancel it
    # so the TUI reader can own the websocket stream instead.
    if delivery._reader_task is not None:
        delivery._reader_task.cancel()
        try:
            await delivery._reader_task
        except asyncio.CancelledError:
            pass
        delivery._reader_task = None

    title = f"OpenClaw WS → agent:{user.get('agentId', '?')}"
    ui = ChatUI(stdscr, title)
    for line in status_lines:
        await ui.add_message(line)

    stop = asyncio.Event()
    async with asyncio.TaskGroup() as tg:
        tg.create_task(gateway_reader(delivery, stop, ui))
        tg.create_task(input_sender(delivery, user, stop, ui))

    await delivery.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive OpenClaw Gateway WS test")
    parser.add_argument("--config-id", default=None, dest="config_id", help="Delivery channel ID (alert_channels.id) — resolves connection and user params automatically")
    parser.add_argument("--channel", default=None, help="Channel config name (alert_channel_configs), used when --config-id is not set")
    parser.add_argument("--agent", default=None, help="Agent ID (overrides delivery channel agentId)")
    parser.add_argument("--session-key", default=None, dest="session_key")
    parser.add_argument("--extra-prompt", default=None, dest="extra_prompt")
    parser.add_argument("--thinking", default=None, choices=["off", "low", "medium", "high"])
    parser.add_argument("--bootstrap", default=None, dest="bootstrap", choices=["lightweight", "full"])
    parser.add_argument("--run-kind", default=None, dest="run_kind", choices=["cron", "heartbeat"])
    parser.add_argument("--deliver", action="store_true", default=False)
    parser.add_argument("--db", default="config/app_data.db", type=Path)
    args = parser.parse_args()

    user: dict = {}
    if args.config_id:
        cfg, user = load_delivery_channel_by_id(args.db, args.config_id)
    elif args.channel:
        cfg = load_channel_config(args.db, args.channel)
    else:
        sys.exit("Provide --config-id <delivery-channel-id> or --channel <name>")

    if cfg["type"] != "openclaw_ws":
        sys.exit(f"Channel {cfg['name']!r} has type {cfg['type']!r}, expected 'openclaw_ws'")

    channel_params: dict = cfg["config"]

    if args.agent:
        user["agentId"] = args.agent
    if args.session_key:
        user["sessionKey"] = args.session_key
    if args.extra_prompt:
        user["extraPrompt"] = args.extra_prompt
    if args.thinking:
        user["thinking"] = args.thinking
    if args.bootstrap:
        user["bootstrapContextMode"] = args.bootstrap
    if args.run_kind:
        user["bootstrapContextRunKind"] = args.run_kind
    if args.deliver:
        user["deliver"] = True

    if not user.get("agentId"):
        sys.exit("No agent ID — provide --agent or --config-id pointing to a delivery channel with an agentId")

    def _run(stdscr) -> None:
        asyncio.run(run(stdscr, channel_params, user))

    try:
        curses.wrapper(_run)
    except KeyboardInterrupt:
        pass
    print("Bye.")


if __name__ == "__main__":
    main()
