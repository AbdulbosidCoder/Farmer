"""Simple JSON storage: chat messages, tasks, recurring tasks and settings.

Everything lives in plain files so Claude Code skills can read them too:
- inbox/telegram/<chat_id>.jsonl   one saved message per line
- out/timetable/tasks.json         all tasks (open and done)
- inbox/telegram/settings.json     report chat, daily time, last scan, recurring tasks
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MSG_DIR = Path(os.getenv("TG_DATA_DIR", ROOT / "inbox" / "telegram"))
OUT_DIR = ROOT / "out" / "timetable"
PLAN_DIR = ROOT / "out" / "plan"
TASKS_FILE = OUT_DIR / "tasks.json"
SETTINGS_FILE = MSG_DIR / "settings.json"

_lock = threading.Lock()

DEFAULT_SETTINGS = {
    "daily_time": os.getenv("DAILY_TIME", "08:00"),
    "report_chat_id": int(os.getenv("REPORT_CHAT_ID")) if os.getenv("REPORT_CHAT_ID") else None,
    "last_scan": None,
    "recurring": [],  # {"id", "days": ["mon",..] or ["daily"], "time": "HH:MM", "title"}
}


def _ensure_dirs() -> None:
    MSG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLAN_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data) -> None:
    _ensure_dirs()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------- settings ----------

def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    data.update(_read_json(SETTINGS_FILE, {}))
    return data


def save_settings(settings: dict) -> None:
    with _lock:
        _write_json(SETTINGS_FILE, settings)


# ---------- messages ----------

def save_message(chat_id: int, chat_title: str, sender: str, date: datetime, text: str, msg_id: int | None = None) -> None:
    _ensure_dirs()
    row = {
        "id": msg_id,
        "chat_id": chat_id,
        "chat": chat_title,
        "from": sender,
        "date": date.isoformat(),
        "text": text,
    }
    with _lock, open(MSG_DIR / f"{chat_id}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_messages(since: datetime | None = None) -> list[dict]:
    """All saved messages from every chat, oldest first, optionally newer than `since`."""
    _ensure_dirs()
    rows: list[dict] = []
    for path in MSG_DIR.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since is not None:
                try:
                    if datetime.fromisoformat(row["date"]) <= since:
                        continue
                except (KeyError, ValueError):
                    continue
            rows.append(row)
    rows.sort(key=lambda r: r.get("date", ""))
    return rows


# ---------- tasks ----------

def _norm(title: str) -> str:
    return re.sub(r"\W+", " ", title.lower()).strip()


def load_tasks() -> list[dict]:
    return _read_json(TASKS_FILE, [])


def save_tasks(tasks: list[dict]) -> None:
    with _lock:
        _write_json(TASKS_FILE, tasks)


def add_tasks(new: list[dict]) -> list[dict]:
    """Add tasks, skipping duplicates (same title and date). Returns the tasks actually added."""
    tasks = load_tasks()
    seen = {(_norm(t["title"]), t.get("date")) for t in tasks}
    next_id = max((t["id"] for t in tasks), default=0) + 1
    added = []
    for t in new:
        title = (t.get("title") or "").strip()
        if not title:
            continue
        key = (_norm(title), t.get("date"))
        if key in seen:
            continue
        seen.add(key)
        task = {
            "id": next_id,
            "title": title,
            "date": t.get("date"),
            "time": t.get("time"),
            "duration_min": int(t.get("duration_min") or 30),
            "owner": t.get("owner"),
            "priority": t.get("priority") or "normal",
            "source": t.get("source"),
            "status": "open",
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        next_id += 1
        tasks.append(task)
        added.append(task)
    save_tasks(tasks)
    return added


def set_status(task_id: int, status: str) -> dict | None:
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            t["status"] = status
            save_tasks(tasks)
            return t
    return None
