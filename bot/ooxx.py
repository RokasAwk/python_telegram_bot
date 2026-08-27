from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .ai import ask_ooxx_move

BOARD_SIZE = 9
EMPTY = " "
USER_MARK = "O"
AI_MARK = "X"

MARK_SYMBOLS = {USER_MARK: "⭕", AI_MARK: "❌"}
POSITION_LABELS = ["１", "２", "３", "４", "５", "６", "７", "８", "９"]

# 直排、橫排、斜排共 8 條連線
WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]

GAME_STATE_KEYS = ("ooxx_active", "ooxx_board")

INTRO = "來玩OOXX啦！\n你是⭕（先手），壽司小狼是❌。\n\n"

# 遊戲結束後才跳出來的按鈕，選完就會銷毀，避免事後誤觸
PLAY_AGAIN_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("離開", callback_data="ooxx:again:no"),
            InlineKeyboardButton("再來一場！", callback_data="ooxx:again:yes"),
        ]
    ]
)


def _new_board() -> list[str]:
    return [EMPTY] * BOARD_SIZE


def _start_game(chat_data) -> None:
    chat_data["ooxx_active"] = True
    chat_data["ooxx_board"] = _new_board()


def _clear_game(chat_data) -> None:
    for key in GAME_STATE_KEYS:
        chat_data.pop(key, None)


def move_keyboard(board: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for r in (0, 3, 6):
        rows.append(
            [
                InlineKeyboardButton(
                    MARK_SYMBOLS[board[i]] if board[i] != EMPTY else POSITION_LABELS[i],
                    callback_data=f"ooxx:move:{i}",
                )
                for i in range(r, r + 3)
            ]
        )
    return InlineKeyboardMarkup(rows)


def _winner(board: list[str]) -> str | None:
    for a, b, c in WIN_LINES:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return board[a]
    return None


def _is_full(board: list[str]) -> bool:
    return EMPTY not in board


def _would_win(board: list[str], idx: int, mark: str) -> bool:
    board[idx] = mark
    won = _winner(board) == mark
    board[idx] = EMPTY
    return won


def _fallback_move(board: list[str]) -> int:
    """AI 沒問到有效答案時的備援：先找自己能贏的，再擋對手，然後搶中間、角落。"""
    empties = [i for i, c in enumerate(board) if c == EMPTY]
    for i in empties:
        if _would_win(board, i, AI_MARK):
            return i
    for i in empties:
        if _would_win(board, i, USER_MARK):
            return i
    for i in (4, 0, 2, 6, 8):
        if i in empties:
            return i
    return empties[0]


async def ooxx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_data = context.chat_data
    if chat_data.get("ooxx_active"):
        await update.message.reply_text("我們還有一場OOXX沒下完啦！輪到你了，快選個格子汪！")
        return

    _start_game(chat_data)
    await update.message.reply_text(
        INTRO + "點下面的格子下手吧！",
        reply_markup=move_keyboard(chat_data["ooxx_board"]),
    )


async def rule_ooxx(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text.strip().upper() != "OOXX":
        return
    await ooxx_command(update, context)
    return True


async def stop_ooxx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_data = context.chat_data
    if not chat_data.get("ooxx_active"):
        await update.message.reply_text("目前沒有進行中的OOXX唷！")
        return

    _clear_game(chat_data)
    await update.message.reply_text("好啦好啦，這場OOXX不算，想玩再跟我說 /ooxx！")


async def _send_result(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    """宣布結果，並附上「離開／再來一場！」按鈕（不再多傳一則訊息）。"""
    context.chat_data["ooxx_active"] = False
    await context.bot.send_message(
        update.effective_chat.id,
        message,
        reply_markup=PLAY_AGAIN_KEYBOARD,
    )


async def handle_ooxx_move_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_data = context.chat_data
    board = chat_data.get("ooxx_board")

    if not chat_data.get("ooxx_active") or board is None:
        await query.answer("這場OOXX已經結束囉，輸入 /ooxx 再開一場！")
        return

    idx = int(query.data.split(":")[2])
    if board[idx] != EMPTY:
        await query.answer("喂喂～那格早就被卡走了啦，換一格啦！😜")
        return

    await query.answer()
    board[idx] = USER_MARK

    if _winner(board) == USER_MARK:
        await _send_result(update, context, "哇賽，你連成一條線了，這場你贏啦！🎉")
        return
    if _is_full(board):
        await _send_result(update, context, "格子填滿了，這場平手！🤝")
        return

    ai_idx = await ask_ooxx_move(board)
    if ai_idx is None or not (0 <= ai_idx < BOARD_SIZE) or board[ai_idx] != EMPTY:
        ai_idx = _fallback_move(board)
    board[ai_idx] = AI_MARK

    if _winner(board) == AI_MARK:
        await _send_result(update, context, f"我下在第 {ai_idx + 1} 格，連成一條線啦，這場我贏！😎")
        return
    if _is_full(board):
        await _send_result(update, context, "格子填滿了，這場平手！🤝")
        return

    await context.bot.send_message(
        update.effective_chat.id,
        f"我下在第 {ai_idx + 1} 格！\n換你了～",
        reply_markup=move_keyboard(board),
    )


async def handle_ooxx_again_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # 先銷毀按鈕，避免事後誤觸
    await query.edit_message_reply_markup(reply_markup=None)

    if query.data.split(":")[2] == "yes":
        _start_game(context.chat_data)
        await context.bot.send_message(
            update.effective_chat.id,
            INTRO + "點下面的格子下手吧！",
            reply_markup=move_keyboard(context.chat_data["ooxx_board"]),
        )
    else:
        _clear_game(context.chat_data)
        await context.bot.send_message(update.effective_chat.id, "好啦，想玩再跟我說 /ooxx！掰掰汪～")
