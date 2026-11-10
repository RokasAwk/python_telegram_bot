"""即時翻譯：/trans_jp、/trans_en 指令，以及 inline mode（輸入框打「@bot jp 文字」即時翻譯）。

指令後面直接接文字 → 直接翻譯；只打指令 → 回一個按鈕，按下去會在輸入框填入「@bot jp 」，
接著打字就會在輸入框上方即時出現翻譯結果，點一下才送出。
inline mode 需要先在 BotFather 用 /setinline 開啟。
"""

import asyncio
import hashlib

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.ext import ContextTypes

from .ai import translate

# inline query 的語言代碼 → (給 Gemini 的語言名稱, 顯示用標題)
LANGUAGES = {
    "jp": ("日文", "🇯🇵 日文"),
    "en": ("英文", "🇺🇸 英文"),
}

# 「送出後由 bot 回覆譯文」按鈕用的前綴 → 語言代碼。
# 這些前綴不是 inline 語言代碼，所以打字過程不會觸發即時翻譯（不呼叫 Gemini），送出後才翻譯一次。
REPLY_KEYWORDS = {
    "翻日文": "jp",
    "翻英文": "en",
}
_REPLY_KEYWORD_BY_LANG = {code: keyword for keyword, code in REPLY_KEYWORDS.items()}

TRANSLATE_FAILED_REPLY = "翻譯失敗了，晚點再試試看～"

# 使用者打字時 Telegram 會連續送出 inline query，等這麼久沒有新的才真的去翻譯，省 Gemini 額度
INLINE_DEBOUNCE_SECONDS = 0.8

# user_id → 該使用者最新一筆 inline query 的 id，用來判斷自己是不是已經被新的輸入取代
_latest_inline_query: dict[int, str] = {}


def _text_after_command(message_text: str | None) -> str:
    """取出指令後面的文字（保留換行），例如「/trans_jp@bot 你好\\n再見」→「你好\\n再見」。"""
    parts = (message_text or "").split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


async def _trans_command(update: Update, lang_code: str):
    language, label = LANGUAGES[lang_code]
    message = update.message
    text = _text_after_command(message.text)

    # 沒接文字但有回覆某則訊息 → 翻譯被回覆的那則
    if not text and message.reply_to_message:
        text = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()

    if not text:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"⚡ 即時翻譯，直接送出{language}",
                        switch_inline_query_current_chat=f"{lang_code} ",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"📋 打完送出，回覆可複製的{language}",
                        switch_inline_query_current_chat=f"{_REPLY_KEYWORD_BY_LANG[lang_code]} ",
                    )
                ],
            ]
        )
        await message.reply_text(
            f"⚡ 即時翻譯：打字時上方會出現{label}譯文，點一下就會以{language}送出\n"
            f"📋 回覆譯文：打完字直接按送出，我會回一則可以複製的{language}譯文\n"
            f"也可以直接打 /trans_{lang_code} 要翻譯的文字",
            reply_markup=keyboard,
        )
        return

    result = await translate(text, language)
    await message.reply_text(result or TRANSLATE_FAILED_REPLY)


async def trans_jp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _trans_command(update, "jp")


async def trans_en_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _trans_command(update, "en")


async def rule_translate_mention(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """處理「@bot 翻日文 文字」（📋 按鈕）和「@bot jp 文字」（⚡ 按鈕但沒點譯文、直接按送出）這種一般訊息，回覆譯文。"""
    mention = f"@{context.bot.username}".lower()
    parts = text.strip().split(maxsplit=2)
    if len(parts) < 3 or parts[0].lower() != mention:
        return
    lang_code = REPLY_KEYWORDS.get(parts[1]) or parts[1].lower()
    if lang_code not in LANGUAGES:
        return
    source = parts[2].strip()
    result = await translate(source, LANGUAGES[lang_code][0])
    await update.message.reply_text(result or TRANSLATE_FAILED_REPLY)
    return True


def _parse_inline_query(query: str) -> tuple[str, str] | None:
    """「jp 今天天氣真好」→ ("jp", "今天天氣真好")；語言代碼不認得或沒有文字時回傳 None。"""
    parts = query.strip().split(maxsplit=1)
    if len(parts) < 2 or parts[0].lower() not in LANGUAGES:
        return None
    return parts[0].lower(), parts[1].strip()


async def handle_translate_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inline_query = update.inline_query
    parsed = _parse_inline_query(inline_query.query)
    if parsed is None:
        await inline_query.answer([], cache_time=0)
        return

    user_id = inline_query.from_user.id
    _latest_inline_query[user_id] = inline_query.id
    await asyncio.sleep(INLINE_DEBOUNCE_SECONDS)
    if _latest_inline_query.get(user_id) != inline_query.id:
        return  # 使用者還在打字，交給較新的那筆 query 處理
    _latest_inline_query.pop(user_id, None)

    lang_code, text = parsed
    language, label = LANGUAGES[lang_code]
    result = await translate(text, language)
    if result is None:
        await inline_query.answer([], cache_time=0)
        return

    result_id = hashlib.md5(f"{lang_code}:{text}".encode()).hexdigest()
    await inline_query.answer(
        [
            InlineQueryResultArticle(
                id=result_id,
                title=f"{label}（點一下送出）",
                description=result,
                input_message_content=InputTextMessageContent(result),
            )
        ],
        cache_time=300,
        is_personal=True,
    )
