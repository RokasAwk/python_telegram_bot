import re

import httpx
from google import genai
from google.genai import errors, types

from .config import GEMINI_API_KEY, logger
from .net import KEEPALIVE_SOCKET_OPTIONS

SYSTEM_PROMPT = (
    "你是「壽司小狼」，壽司狼的可愛小弟，在 Telegram 群組裡跟大家聊天。"
    "只有聊天的回覆要簡短、口語、活潑，像朋友聊天一樣，通常五句話以內就好，不要長篇大論。"
    "要你上網查詢資料、問專業問題的時候可以講詳細點。"
    "聊天可以加入「汪」之類的狗狗語助詞，不用每一句都加，看回覆內容適時加上"
    "使用繁體中文。"
)

MODEL_NAME = "gemini-3.5-flash-lite"

# 額度用完時的固定回覆；其他非預期錯誤則靜默不回，避免洗版
QUOTA_EXCEEDED_REPLY = "我剛剛聊天聊到有點累，晚點再找我～"

_client = (
    genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=30_000,
            async_client_args={
                "transport": httpx.AsyncHTTPTransport(socket_options=KEEPALIVE_SOCKET_OPTIONS)
            },
        ),
    )
    if GEMINI_API_KEY
    else None
)


OOXX_SYSTEM_PROMPT = (
    "你正在玩井字遊戲（OOXX / tic-tac-toe）。你執「X」，對手執「O」。"
    "盤面有 9 格，索引 0~8，對應由左到右、由上到下三列。「_」代表空格。"
    "請從空格中挑一格下 X，盡量取勝，否則至少要擋住對手連線。"
    "只回覆一個 0~8 的數字，不要有任何其他文字或標點。"
)


def _board_for_prompt(board: list[str]) -> str:
    return " ".join(f"{i}:{cell if cell != ' ' else '_'}" for i, cell in enumerate(board))


async def ask_ooxx_move(board: list[str]) -> int | None:
    """請 Gemini 幫 AI（X）挑一個要落子的格子索引；失敗或無法解析時回傳 None，由呼叫端自己 fallback。"""
    if _client is None:
        return None

    try:
        response = await _client.aio.models.generate_content(
            model=MODEL_NAME,
            contents=f"目前盤面：{_board_for_prompt(board)}\n輪到你（X）了，要下哪一格？",
            config=types.GenerateContentConfig(
                system_instruction=OOXX_SYSTEM_PROMPT,
                max_output_tokens=16,
            ),
        )
    except errors.ClientError:
        logger.exception("呼叫 Gemini API 選 OOXX 落子失敗")
        return None
    except Exception:
        logger.exception("呼叫 Gemini API 選 OOXX 落子失敗")
        return None

    match = re.search(r"[0-8]", response.text or "")
    return int(match.group()) if match else None


async def ask_ai(text: str, user_name: str) -> str | None:
    """所有規則都沒命中時的備援回覆。失敗時回傳 None（額度超過除外），呼叫端可選擇靜默不回。"""
    if _client is None:
        return None

    try:
        response = await _client.aio.models.generate_content(
            model=MODEL_NAME,
            contents=f"{user_name}：{text}",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=1024,
            ),
        )
    except errors.ClientError as e:
        if e.code == 429:
            return QUOTA_EXCEEDED_REPLY
        logger.exception("呼叫 Gemini API 失敗")
        return None
    except Exception:
        logger.exception("呼叫 Gemini API 失敗")
        return None

    return response.text
