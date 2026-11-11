import os
import sqlite3

import pytest

import bot.notes as notes
from telegram import ForceReply
from telegram.constants import ParseMode

from bot.notes import (
    EDITING_KEY,
    cancel_note_editing,
    delnote_command,
    editnote_command,
    note_command,
    notes_command,
    rule_editing_note,
)
from bot.text_dispatch import handle_text
from tests.conftest import MakeUpdate


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """每個測試用自己的暫存資料庫，資料夾不存在也要能自動建立。"""
    db_path = str(tmp_path / "nested" / "notes.db")
    monkeypatch.setattr(notes, "NOTES_DB_PATH", db_path)
    return db_path


def _reply_texts(update):
    return [call.args[0] for call in update.message.reply_text.call_args_list]


async def test_note_saves_and_notes_lists_it(make_update, make_context):
    await note_command(make_update("/note 買牛奶"), make_context())

    update = make_update("/notes")
    await notes_command(update, make_context())

    (text,) = _reply_texts(update)
    assert text.startswith("<code>1. ")
    assert "買牛奶" in text


async def test_note_keeps_multiline_content(make_update, make_context):
    await note_command(make_update("/note 第一行\n第二行"), make_context())

    update = make_update("/notes")
    await notes_command(update, make_context())

    assert "第一行\n第二行" in _reply_texts(update)[0]


async def test_note_with_bot_username_suffix(make_update, make_context):
    await note_command(make_update("/note@sushi_bot 群組裡記的"), make_context())

    update = make_update("/notes")
    await notes_command(update, make_context())

    assert "群組裡記的" in _reply_texts(update)[0]


async def test_note_without_content_shows_usage(make_update, make_context, temp_db):
    update = make_update("/note")
    await note_command(update, make_context())

    assert "用法" in _reply_texts(update)[0]
    assert notes.list_notes(temp_db, 111) == []


async def test_note_too_long_is_rejected(make_update, make_context, temp_db):
    update = make_update("/note " + "字" * (notes.NOTE_MAX_LENGTH + 1))
    await note_command(update, make_context())

    assert "太長" in _reply_texts(update)[0]
    assert notes.list_notes(temp_db, 111) == []


async def test_notes_list_uses_html_and_escapes_content(make_update, make_context):
    await note_command(make_update("/note <b>a & b</b>"), make_context())

    update = make_update("/notes")
    await notes_command(update, make_context())

    (text,), kwargs = update.message.reply_text.call_args
    assert kwargs["parse_mode"] == ParseMode.HTML
    assert "<blockquote>&lt;b&gt;a &amp; b&lt;/b&gt;</blockquote>" in text


async def test_notes_empty(make_update, make_context):
    update = make_update("/notes")
    await notes_command(update, make_context())

    assert "還沒有任何筆記" in _reply_texts(update)[0]


async def test_notes_are_per_user(make_context):
    alice = MakeUpdate(user_id=1)
    bob = MakeUpdate(user_id=2)
    await note_command(alice("/note 小明的秘密"), make_context())

    update = bob("/notes")
    await notes_command(update, make_context())

    assert "還沒有任何筆記" in _reply_texts(update)[0]


async def test_delnote_removes_by_display_index(make_update, make_context, temp_db):
    for text in ("一", "二", "三"):
        await note_command(make_update(f"/note {text}"), make_context())

    update = make_update("/delnote 2")
    await delnote_command(update, make_context())

    assert "二" in _reply_texts(update)[0]
    assert [content for _, content, _, _ in notes.list_notes(temp_db, 111)] == ["一", "三"]


async def test_delnote_cannot_delete_other_users_note(make_context, temp_db):
    await note_command(MakeUpdate(user_id=1)("/note 別人的"), make_context())

    update = MakeUpdate(user_id=2)("/delnote 1")
    await delnote_command(update, make_context())

    assert "找不到" in _reply_texts(update)[0]
    assert len(notes.list_notes(temp_db, 1)) == 1


@pytest.mark.parametrize("text", ["/delnote", "/delnote abc", "/delnote 0", "/delnote -1"])
async def test_delnote_invalid_argument_shows_usage(make_update, make_context, text):
    update = make_update(text)
    await delnote_command(update, make_context())

    assert "用法" in _reply_texts(update)[0]


async def test_delnote_out_of_range(make_update, make_context):
    await note_command(make_update("/note 只有一筆"), make_context())

    update = make_update("/delnote 5")
    await delnote_command(update, make_context())

    assert "找不到第 5 筆" in _reply_texts(update)[0]


async def test_editnote_updates_content_and_keeps_order(make_update, make_context, temp_db):
    for text in ("一", "二", "三"):
        await note_command(make_update(f"/note {text}"), make_context())

    update = make_update("/editnote 2 改過的二")
    await editnote_command(update, make_context())

    assert _reply_texts(update) == ["第 2 筆筆記改好了！✏️"]
    assert [content for _, content, _, _ in notes.list_notes(temp_db, 111)] == ["一", "改過的二", "三"]


async def test_editnote_keeps_multiline_content(make_update, make_context, temp_db):
    await note_command(make_update("/note 舊的"), make_context())

    await editnote_command(make_update("/editnote 1\n第一行\n第二行"), make_context())

    assert notes.list_notes(temp_db, 111)[0][1] == "第一行\n第二行"


async def test_editnote_cannot_edit_other_users_note(make_context, temp_db):
    await note_command(MakeUpdate(user_id=1)("/note 別人的"), make_context())

    update = MakeUpdate(user_id=2)("/editnote 1 偷改")
    await editnote_command(update, make_context())

    assert "找不到" in _reply_texts(update)[0]
    assert notes.list_notes(temp_db, 1)[0][1] == "別人的"


@pytest.mark.parametrize(
    "text", ["/editnote", "/editnote abc 內容", "/editnote 0 內容", "/editnote 新內容"]
)
async def test_editnote_invalid_argument_shows_usage(make_update, make_context, text):
    update = make_update(text)
    await editnote_command(update, make_context())

    assert "用法" in _reply_texts(update)[0]


async def test_editnote_out_of_range(make_update, make_context):
    await note_command(make_update("/note 只有一筆"), make_context())

    update = make_update("/editnote 5 內容")
    await editnote_command(update, make_context())

    assert "找不到第 5 筆" in _reply_texts(update)[0]


async def test_editnote_too_long_is_rejected(make_update, make_context, temp_db):
    await note_command(make_update("/note 原本"), make_context())

    update = make_update("/editnote 1 " + "字" * (notes.NOTE_MAX_LENGTH + 1))
    await editnote_command(update, make_context())

    assert "太長" in _reply_texts(update)[0]
    assert notes.list_notes(temp_db, 111)[0][1] == "原本"


async def test_notes_shows_year_and_edited_marker(make_update, make_context, monkeypatch):
    times = iter(["2025-12-31T16:05:00+00:00", "2026-03-02T01:30:00+00:00"])
    monkeypatch.setattr(notes, "_now", lambda: next(times))
    await note_command(make_update("/note 原本"), make_context())
    await editnote_command(make_update("/editnote 1 改過"), make_context())

    update = make_update("/notes")
    await notes_command(update, make_context())

    # UTC 2025-12-31 16:05 = 台灣 2026/01/01 00:05（跨年也要正確）
    assert (
        "<code>1. 2026/01/01 00:05</code>\n"
        "<code>編輯於 2026/03/02 09:30</code>\n"
        f"<code>{'-' * 25}</code>\n"
        "<blockquote>改過</blockquote>"
    ) in _reply_texts(update)[0]


async def test_notes_unedited_has_no_marker(make_update, make_context, monkeypatch):
    monkeypatch.setattr(notes, "_now", lambda: "2026-11-11T06:00:00+00:00")
    await note_command(make_update("/note 沒改過"), make_context())

    update = make_update("/notes")
    await notes_command(update, make_context())

    text = _reply_texts(update)[0]
    assert (
        "<code>1. 2026/11/11 14:00</code>\n"
        f"<code>{'-' * 25}</code>\n"
        "<blockquote>沒改過</blockquote>"
    ) in text
    assert "編輯於" not in text


def test_old_database_without_updated_at_is_migrated(temp_db):
    """上一版的資料表沒有 updated_at 欄位，打開時要自動補上，舊筆記保留。"""
    os.makedirs(os.path.dirname(temp_db), exist_ok=True)
    with sqlite3.connect(temp_db) as conn:
        conn.execute(
            "CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,"
            " content TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO notes (user_id, content, created_at) VALUES (111, '舊筆記', '2026-11-01T00:00:00+00:00')"
        )
    conn.close()

    assert notes.list_notes(temp_db, 111) == [(1, "舊筆記", "2026-11-01T00:00:00+00:00", None)]
    assert notes.update_note(temp_db, 111, 1, "新內容") == "舊筆記"
    assert notes.list_notes(temp_db, 111)[0][3] is not None


async def test_notes_survive_reopening_database(make_update, make_context, temp_db):
    """模擬容器重建：同一個檔案路徑重新開連線，資料要還在。"""
    await note_command(make_update("/note 重建後還在"), make_context())

    assert notes.list_notes(temp_db, 111)[0][1] == "重建後還在"


def test_chunk_lines_splits_long_output():
    lines = ["a" * 3000, "b" * 3000, "c" * 10]
    chunks = notes._chunk_lines(lines, limit=4000)

    assert len(chunks) == 2
    assert chunks[0] == "a" * 3000
    assert chunks[1] == "b" * 3000 + "\n\n" + "c" * 10


# ---- 「/editnote 編號」→ 問要改成什麼 → 下一則訊息當新內容 ----


async def test_editnote_with_only_index_asks_and_shows_original(make_update, make_context):
    await note_command(make_update("/note 買牛奶\n買蛋"), make_context())
    context = make_context()

    update = make_update("/editnote 1")
    await editnote_command(update, context)

    (text,), kwargs = update.message.reply_text.call_args
    assert "要把第 1 筆改成什麼" in text
    assert "<pre>買牛奶\n買蛋</pre>" in text
    assert kwargs["parse_mode"] == ParseMode.HTML
    assert isinstance(kwargs["reply_markup"], ForceReply)
    assert context.user_data[EDITING_KEY]["index"] == 1


async def test_editnote_original_content_is_html_escaped(make_update, make_context):
    await note_command(make_update("/note <b>a & b</b>"), make_context())

    update = make_update("/editnote 1")
    await editnote_command(update, make_context())

    assert "<pre>&lt;b&gt;a &amp; b&lt;/b&gt;</pre>" in _reply_texts(update)[0]


async def test_next_message_becomes_new_content(make_update, make_context, temp_db):
    await note_command(make_update("/note 舊的"), make_context())
    context = make_context()
    await editnote_command(make_update("/editnote 1"), context)

    update = make_update("新的\n第二行")
    assert await rule_editing_note(update, context, update.message.text) is True

    assert _reply_texts(update) == ["第 1 筆筆記改好了！✏️"]
    assert notes.list_notes(temp_db, 111)[0][1] == "新的\n第二行"
    assert EDITING_KEY not in context.user_data


async def test_handle_text_routes_to_editing_before_other_rules(make_update, make_context, temp_db):
    """等待新內容時，就算訊息像是要觸發其他功能（例如問 bot 能幹嘛），也要當成筆記內容。"""
    await note_command(make_update("/note 舊的"), make_context())
    context = make_context()
    await editnote_command(make_update("/editnote 1"), context)

    await handle_text(make_update("這個機器人可以幹嘛？"), context)

    assert notes.list_notes(temp_db, 111)[0][1] == "這個機器人可以幹嘛？"


async def test_editnote_index_not_found_does_not_start_editing(make_update, make_context):
    context = make_context()

    update = make_update("/editnote 3")
    await editnote_command(update, context)

    assert "找不到第 3 筆" in _reply_texts(update)[0]
    assert EDITING_KEY not in context.user_data


async def test_not_editing_rule_does_nothing(make_update, make_context):
    update = make_update("隨便聊聊")
    assert await rule_editing_note(update, make_context(), "隨便聊聊") is None
    update.message.reply_text.assert_not_awaited()


async def test_message_in_other_chat_is_not_taken_as_content(make_context, temp_db):
    await note_command(MakeUpdate(chat_id=1)("/note 舊的"), make_context())
    context = make_context()
    await editnote_command(MakeUpdate(chat_id=1)("/editnote 1"), context)

    update = MakeUpdate(chat_id=2)("在別的群組講話")
    assert await rule_editing_note(update, context, update.message.text) is None

    assert notes.list_notes(temp_db, 111)[0][1] == "舊的"
    assert EDITING_KEY in context.user_data


async def test_any_command_cancels_editing(make_update, make_context, temp_db):
    await note_command(make_update("/note 舊的"), make_context())
    context = make_context()
    await editnote_command(make_update("/editnote 1"), context)

    await cancel_note_editing(make_update("/notes"), context)
    update = make_update("之後的聊天")
    assert await rule_editing_note(update, context, update.message.text) is None

    assert notes.list_notes(temp_db, 111)[0][1] == "舊的"


async def test_edit_targets_same_note_even_if_numbering_shifts(make_update, make_context, temp_db):
    """問完要改成什麼之後先刪掉前面一筆，編號位移了，還是要改到原本選的那筆。"""
    for text in ("一", "二"):
        await note_command(make_update(f"/note {text}"), make_context())
    context = make_context()
    await editnote_command(make_update("/editnote 2"), context)
    await delnote_command(make_update("/delnote 1"), make_context())

    update = make_update("改過的二")
    await rule_editing_note(update, context, update.message.text)

    assert [content for _, content, _, _ in notes.list_notes(temp_db, 111)] == ["改過的二"]


async def test_edit_when_note_was_deleted_meanwhile(make_update, make_context, temp_db):
    await note_command(make_update("/note 會被刪掉"), make_context())
    context = make_context()
    await editnote_command(make_update("/editnote 1"), context)
    await delnote_command(make_update("/delnote 1"), make_context())

    update = make_update("新內容")
    await rule_editing_note(update, context, update.message.text)

    assert "已經不在" in _reply_texts(update)[0]
    assert notes.list_notes(temp_db, 111) == []
    assert EDITING_KEY not in context.user_data


async def test_too_long_new_content_keeps_waiting(make_update, make_context, temp_db):
    await note_command(make_update("/note 原本"), make_context())
    context = make_context()
    await editnote_command(make_update("/editnote 1"), context)

    long_text = "字" * (notes.NOTE_MAX_LENGTH + 1)
    update = make_update(long_text)
    await rule_editing_note(update, context, long_text)

    assert "太長" in _reply_texts(update)[0]
    assert notes.list_notes(temp_db, 111)[0][1] == "原本"
    assert EDITING_KEY in context.user_data
