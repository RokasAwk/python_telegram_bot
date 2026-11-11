"""記事本：每個使用者各自的筆記，存在 SQLite。

資料庫檔預設在 data/notes.db（容器裡是 /app/data/notes.db），部署時要把這個資料夾
用 bind mount 掛到主機上，否則容器被刪掉重建時筆記會跟著不見。
"""

import asyncio
import html
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone

from telegram import ForceReply, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .config import NOTES_DB_PATH

# 台灣沒有日光節約時間，直接用固定 +8，不依賴容器裡有沒有裝 tzdata
TAIPEI_TZ = timezone(timedelta(hours=8))

# Telegram 單則訊息上限 4096 字，留點空間給前綴
NOTE_MAX_LENGTH = 4000
MESSAGE_CHUNK_LIMIT = 4000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    content    TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_notes_user_id ON notes (user_id);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """舊版資料表沒有 updated_at，補上欄位（CREATE TABLE IF NOT EXISTS 不會幫已存在的表加欄位）。"""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(notes)")}
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE notes ADD COLUMN updated_at TEXT")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect(db_path: str):
    """開連線、確保資料表存在；區塊正常結束就 commit、出錯就 rollback，最後一定關閉連線。"""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        with conn:
            yield conn


def add_note(db_path: str, user_id: int, content: str) -> None:
    created_at = _now()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO notes (user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content, created_at),
        )


def list_notes(db_path: str, user_id: int) -> list[tuple[int, str, str, str | None]]:
    """回傳 (id, content, created_at, updated_at)，依建立順序排列；沒編輯過的 updated_at 是 None。"""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, content, created_at, updated_at FROM notes WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return rows


def delete_note(db_path: str, user_id: int, index: int) -> str | None:
    """刪掉使用者第 index 筆筆記（從 1 開始，跟 /notes 顯示的編號一致），回傳被刪的內容；編號不存在回傳 None。"""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, content FROM notes WHERE user_id = ? ORDER BY id LIMIT 1 OFFSET ?",
            (user_id, index - 1),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM notes WHERE id = ?", (row[0],))
    return row[1]


def update_note(db_path: str, user_id: int, index: int, content: str) -> str | None:
    """把使用者第 index 筆筆記改成 content，回傳修改前的內容；編號不存在回傳 None。"""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, content FROM notes WHERE user_id = ? ORDER BY id LIMIT 1 OFFSET ?",
            (user_id, index - 1),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE notes SET content = ?, updated_at = ? WHERE id = ?",
            (content, _now(), row[0]),
        )
    return row[1]


def get_note(db_path: str, user_id: int, index: int) -> tuple[int, str] | None:
    """取使用者第 index 筆筆記的 (id, content)；編號不存在回傳 None。"""
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT id, content FROM notes WHERE user_id = ? ORDER BY id LIMIT 1 OFFSET ?",
            (user_id, index - 1),
        ).fetchone()


def update_note_by_id(db_path: str, user_id: int, note_id: int, content: str) -> bool:
    """用資料庫 id 改筆記（限本人），筆記已不存在回傳 False。"""
    with _connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE notes SET content = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (content, _now(), note_id, user_id),
        )
    return cursor.rowcount > 0


def _command_argument(text: str | None) -> str:
    """取出指令後面的內容（保留換行），例如 "/note 買牛奶\n買蛋" -> "買牛奶\n買蛋"。"""
    parts = (text or "").split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _format_time(iso_time: str) -> str:
    return datetime.fromisoformat(iso_time).astimezone(TAIPEI_TZ).strftime("%Y/%m/%d %H:%M")


NOTE_SEPARATOR = "-" * 25


def _format_note(index: int, content: str, created_at: str, updated_at: str | None) -> str:
    """一筆筆記的 HTML（送出時要用 ParseMode.HTML），時間和分隔線用等寬字，內容放在 Telegram 的引用區塊裡。"""
    header = [f"{index}. {_format_time(created_at)}"]
    if updated_at:
        header.append(f"編輯於 {_format_time(updated_at)}")
    header.append(NOTE_SEPARATOR)
    # 時間和分隔線用等寬字（<code>），每行各包一次，避免變成有複製按鈕的 <pre> 區塊
    lines = [f"<code>{line}</code>" for line in header]
    lines.append(f"<blockquote>{html.escape(content)}</blockquote>")
    return "\n".join(lines)


def _chunk_lines(lines: list[str], limit: int = MESSAGE_CHUNK_LIMIT) -> list[str]:
    chunks, current = [], ""
    for line in lines:
        candidate = f"{current}\n\n{line}" if current else line
        if len(candidate) > limit and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = _command_argument(update.message.text)
    if not content:
        await update.message.reply_text("要記什麼呢？用法：/note 要記下來的內容")
        return
    if len(content) > NOTE_MAX_LENGTH:
        await update.message.reply_text(f"太長了啦！一筆筆記最多 {NOTE_MAX_LENGTH} 個字。")
        return

    await asyncio.to_thread(add_note, NOTES_DB_PATH, update.effective_user.id, content)
    await update.message.reply_text("記下來了！📝 用 /notes 可以看所有筆記。")


async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await asyncio.to_thread(list_notes, NOTES_DB_PATH, update.effective_user.id)
    if not rows:
        await update.message.reply_text("你還沒有任何筆記喔！用 /note 內容 來記一筆吧。")
        return

    lines = [
        _format_note(i, content, created_at, updated_at)
        for i, (_, content, created_at, updated_at) in enumerate(rows, start=1)
    ]
    lines.append("編輯筆記：/editnote 編號\n刪除筆記：/delnote 編號")
    # 只在筆記之間切訊息，不會把 <blockquote> 切成兩半
    for chunk in _chunk_lines(lines):
        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def delnote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    arg = _command_argument(update.message.text)
    if not arg.isdigit() or int(arg) < 1:
        await update.message.reply_text("要刪哪一筆呢？用法：/delnote 編號（編號看 /notes）")
        return

    deleted = await asyncio.to_thread(
        delete_note, NOTES_DB_PATH, update.effective_user.id, int(arg)
    )
    if deleted is None:
        await update.message.reply_text(f"找不到第 {arg} 筆筆記，用 /notes 確認一下編號吧。")
        return
    await update.message.reply_text(f"已刪除第 {arg} 筆筆記：\n{deleted}")


# 「/editnote 編號」之後等使用者輸入新內容的狀態，存在 context.user_data
EDITING_KEY = "editing_note"


async def editnote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # "/editnote 2" -> 問要改成什麼；"/editnote 2 新內容" -> 直接改（新內容可以換行）
    parts = _command_argument(update.message.text).split(maxsplit=1)
    index = parts[0] if parts else ""
    content = parts[1].strip() if len(parts) > 1 else ""
    if not index.isdigit() or int(index) < 1:
        await update.message.reply_text(
            "要改哪一筆呢？用法：/editnote 編號（編號看 /notes）"
        )
        return

    if not content:
        await _ask_for_new_content(update, context, int(index))
        return

    if len(content) > NOTE_MAX_LENGTH:
        await update.message.reply_text(f"太長了啦！一筆筆記最多 {NOTE_MAX_LENGTH} 個字。")
        return
    old = await asyncio.to_thread(
        update_note, NOTES_DB_PATH, update.effective_user.id, int(index), content
    )
    if old is None:
        await update.message.reply_text(f"找不到第 {index} 筆筆記，用 /notes 確認一下編號吧。")
        return
    await update.message.reply_text(f"第 {index} 筆筆記改好了！✏️")


async def _ask_for_new_content(update: Update, context: ContextTypes.DEFAULT_TYPE, index: int):
    note = await asyncio.to_thread(get_note, NOTES_DB_PATH, update.effective_user.id, index)
    if note is None:
        await update.message.reply_text(f"找不到第 {index} 筆筆記，用 /notes 確認一下編號吧。")
        return

    note_id, content = note
    # 記資料庫 id 而不是編號：等待期間如果刪了別筆，編號會位移，id 不會
    # 記 chat_id：user_data 是跨聊天室共用的，只吃同一個聊天室裡的下一則訊息
    context.user_data[EDITING_KEY] = {
        "note_id": note_id,
        "index": index,
        "chat_id": update.effective_chat.id,
    }
    # 原文放在 <pre> 程式碼框，Telegram 會顯示複製按鈕，方便貼回輸入框修改
    # ForceReply：自動切到「回覆這則訊息」，群組開了隱私模式時 bot 也收得到回覆
    await update.message.reply_text(
        f"要把第 {index} 筆改成什麼呢？直接回覆這則訊息就好。\n"
        "（打其他指令就會取消編輯）\n\n"
        f"原本的內容（點一下可以複製）：\n<pre>{html.escape(content)}</pre>",
        parse_mode=ParseMode.HTML,
        reply_markup=ForceReply(selective=True, input_field_placeholder="輸入新的內容"),
    )


async def rule_editing_note(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """正在等新內容時，把這則訊息當成筆記的新內容。"""
    editing = context.user_data.get(EDITING_KEY)
    if not editing or editing["chat_id"] != update.effective_chat.id:
        return

    content = text.strip()
    if len(content) > NOTE_MAX_LENGTH:
        await update.message.reply_text(
            f"太長了啦！一筆筆記最多 {NOTE_MAX_LENGTH} 個字，再傳一次短一點的吧。"
        )
        return True

    context.user_data.pop(EDITING_KEY)
    updated = await asyncio.to_thread(
        update_note_by_id, NOTES_DB_PATH, update.effective_user.id, editing["note_id"], content
    )
    if not updated:
        await update.message.reply_text("這筆筆記已經不在了，可能剛剛被刪掉了。")
        return True
    await update.message.reply_text(f"第 {editing['index']} 筆筆記改好了！✏️")
    return True


async def cancel_note_editing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """任何指令都會取消等待中的編輯（在其他 handler 之前跑，不攔截指令本身）。"""
    context.user_data.pop(EDITING_KEY, None)
