from google import genai
from google.genai import errors, types

from .config import GEMINI_API_KEY, logger

SYSTEM_PROMPT = (
    "你是「壽司小狼」，壽司狼的可愛小弟，在 Telegram 群組裡跟大家聊天。"
    "回覆要簡短、口語、活潑，像朋友聊天一樣，通常一兩句話就好，不要長篇大論。"
    "使用繁體中文。"
)

MODEL_NAME = "gemini-3.5-flash-lite"

# 額度用完時的固定回覆；其他非預期錯誤則靜默不回，避免洗版
QUOTA_EXCEEDED_REPLY = "我剛剛聊天聊到有點累，晚點再找我～"

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


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
