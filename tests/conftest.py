"""共用的 pytest fixtures：組出假的 telegram Update / Context，讓 handler 測試不用真的連 Telegram。"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import ContextTypes


class MakeUpdate:
    """呼叫一次可以做出一個文字訊息的 Update，也可以之後接上 make_callback_update 需要的欄位。"""

    def __init__(self, user_id=111, first_name="小明", chat_id=999):
        self.user_id = user_id
        self.first_name = first_name
        self.chat_id = chat_id

    def __call__(self, text=None):
        user = MagicMock(spec=User)
        user.id = self.user_id
        user.first_name = self.first_name

        chat = MagicMock(spec=Chat)
        chat.id = self.chat_id

        message = MagicMock(spec=Message)
        message.text = text
        message.message_id = 1
        message.reply_text = AsyncMock()

        update = MagicMock(spec=Update)
        update.message = message
        update.effective_user = user
        update.effective_chat = chat
        update.callback_query = None
        return update


@pytest.fixture
def make_update():
    return MakeUpdate()


@pytest.fixture
def make_callback_update(make_update):
    """組出一個帶 callback_query 的 Update（模擬使用者點了 inline keyboard 按鈕）。"""

    def _make(callback_data: str):
        update = make_update()
        query = MagicMock(spec=CallbackQuery)
        query.data = callback_data
        query.answer = AsyncMock()
        query.message = MagicMock(spec=Message)
        query.message.message_id = 2
        update.callback_query = query
        return update

    return _make


@pytest.fixture
def make_context():
    def _make():
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = MagicMock()
        context.bot.send_message = AsyncMock()
        context.bot.send_sticker = AsyncMock()
        context.chat_data = {}
        context.user_data = {}
        return context

    return _make
