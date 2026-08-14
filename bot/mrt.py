import time

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .config import TDX_API_BASE_URL, TDX_AUTH_URL, TDX_CLIENT_ID, TDX_CLIENT_SECRET, logger

# TDX 目前只有這幾個軌道系統同時支援「車站出入口」跟「車站設施」兩支 API
# （貓空纜車 TRTCMG 有出入口資料但沒有設施資料，先不放進選單）
RAIL_SYSTEMS = {
    "TRTC": "臺北捷運",
    "NTMC": "新北捷運",
    "TYMC": "桃園捷運",
    "TMRT": "臺中捷運",
    "KRTC": "高雄捷運",
}
SYSTEM_BUTTONS_PER_ROW = 3
LINE_BUTTONS_PER_ROW = 2
STATION_BUTTONS_PER_ROW = 4

# 出入口跟設施資料變動不頻繁，快取一段時間避免每次點站名都重打 TDX API
DATA_CACHE_TTL_SECONDS = 3600

# TDX Escalator 欄位：0:沒有,1:雙向,2:出站(往上),3:入站(往下)
ESCALATOR_SYMBOLS = {0: "❌", 1: "↕️", 2: "⬆️", 3: "⬇️"}
YES_NO_SYMBOLS = {True: "⭕", False: "❌"}

_token_cache = {"access_token": None, "expires_at": 0.0}
_station_cache = {}  # rail_system -> {"expires_at": ts, "stations": {station_id: {...}}}
_line_cache = {}  # rail_system -> {"expires_at": ts, "lines": {line_id: {"name": ..., "stations": [(id, name), ...]}}}


def chunk(items, size):
    return [items[i : i + size] for i in range(0, len(items), size)]


async def _get_access_token() -> str | None:
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now:
        return _token_cache["access_token"]

    if not (TDX_CLIENT_ID and TDX_CLIENT_SECRET):
        return None

    data = {
        "grant_type": "client_credentials",
        "client_id": TDX_CLIENT_ID,
        "client_secret": TDX_CLIENT_SECRET,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(TDX_AUTH_URL, data=data)
            resp.raise_for_status()
            token_data = resp.json()
    except httpx.HTTPError:
        logger.exception("取得 TDX access token 失敗")
        return None

    _token_cache["access_token"] = token_data["access_token"]
    _token_cache["expires_at"] = now + token_data["expires_in"] - 60
    return _token_cache["access_token"]


async def _tdx_get(path: str) -> list | None:
    token = await _get_access_token()
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{TDX_API_BASE_URL}{path}", params={"$format": "JSON"}, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        logger.exception("查詢 TDX API 失敗：%s", path)
        return None


async def _load_system_stations(rail_system: str) -> dict | None:
    cached = _station_cache.get(rail_system)
    now = time.time()
    if cached and cached["expires_at"] > now:
        return cached["stations"]

    exits = await _tdx_get(f"/v2/Rail/Metro/StationExit/{rail_system}")
    if exits is None:
        return None
    # 設施資料抓不到時，寧可先回傳只有出入口的資料，也不要把「暫時打不到」
    # 快取成「這站真的沒有廁所/電梯」，不然使用者要等快取過期才會再看到正確資料
    facilities = await _tdx_get(f"/v2/Rail/Metro/StationFacility/{rail_system}")

    stations = {}
    for item in exits:
        station = stations.setdefault(
            item["StationID"],
            {"name": item["StationName"]["Zh_tw"], "exits": [], "elevators": [], "toilets": []},
        )
        station["exits"].append(item)

    for item in facilities or []:
        station = stations.setdefault(
            item["StationID"],
            {"name": item["StationName"]["Zh_tw"], "exits": [], "elevators": [], "toilets": []},
        )
        station["elevators"] = item.get("Elevators") or []
        station["toilets"] = item.get("Toilets") or []

    if facilities is not None:
        _station_cache[rail_system] = {"expires_at": now + DATA_CACHE_TTL_SECONDS, "stations": stations}
    return stations


async def _load_system_lines(rail_system: str) -> dict | None:
    cached = _line_cache.get(rail_system)
    now = time.time()
    if cached and cached["expires_at"] > now:
        return cached["lines"]

    lines_data = await _tdx_get(f"/v2/Rail/Metro/Line/{rail_system}")
    if lines_data is None:
        return None
    # StationOfLine 一定要拿到才能組出每條線的車站，失敗就整批放棄，
    # 不能把「暫時打不到」的線當成「這條線真的沒有車站」快取起來
    stations_of_line = await _tdx_get(f"/v2/Rail/Metro/StationOfLine/{rail_system}")
    if stations_of_line is None:
        return None
    stations_by_line = {item["LineID"]: item["Stations"] for item in stations_of_line}

    lines = {}
    for item in lines_data:
        line_id = item["LineID"]
        stations = sorted(stations_by_line.get(line_id, []), key=lambda s: s["Sequence"])
        lines[line_id] = {
            "name": item["LineName"]["Zh_tw"],
            "stations": [(s["StationID"], s["StationName"]["Zh_tw"]) for s in stations],
        }

    _line_cache[rail_system] = {"expires_at": now + DATA_CACHE_TTL_SECONDS, "lines": lines}
    return lines


async def mrt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = chunk(list(RAIL_SYSTEMS.items()), SYSTEM_BUTTONS_PER_ROW)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(name, callback_data=f"mrt:system:{code}") for code, name in row] for row in rows]
    )
    await update.message.reply_text("要查哪個軌道系統的車站出入口呢？", reply_markup=keyboard)


async def handle_mrt_system_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    rail_system = query.data.split(":", 2)[2]
    await query.answer()
    system_name = RAIL_SYSTEMS.get(rail_system, rail_system)

    if not (TDX_CLIENT_ID and TDX_CLIENT_SECRET):
        await context.bot.send_message(
            update.effective_chat.id,
            "還沒設定 TDX_CLIENT_ID / TDX_CLIENT_SECRET，小狼查不到捷運資料，跟壽司狼哥哥說一下吧！",
            reply_to_message_id=query.message.message_id,
        )
        return

    lines = await _load_system_lines(rail_system)
    if not lines:
        await context.bot.send_message(
            update.effective_chat.id,
            f"查不到{system_name}的路線資料欸，晚點再試試看！",
            reply_to_message_id=query.message.message_id,
        )
        return

    sorted_lines = sorted(lines.items(), key=lambda kv: kv[0])
    rows = chunk(sorted_lines, LINE_BUTTONS_PER_ROW)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(info["name"], callback_data=f"mrt:line:{rail_system}:{line_id}")
                for line_id, info in row
            ]
            for row in rows
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        f"{system_name}要查哪條路線呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


async def handle_mrt_line_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, rail_system, line_id = query.data.split(":", 3)
    await query.answer()

    lines = await _load_system_lines(rail_system)
    line = lines.get(line_id) if lines else None
    if not line or not line["stations"]:
        await context.bot.send_message(
            update.effective_chat.id,
            "查不到這條路線的車站資料欸，晚點再試試看！",
            reply_to_message_id=query.message.message_id,
        )
        return

    rows = chunk(line["stations"], STATION_BUTTONS_PER_ROW)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(name, callback_data=f"mrt:station:{rail_system}:{sid}") for sid, name in row]
            for row in rows
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        f"{line['name']}要查哪一站呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


async def handle_mrt_station_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, rail_system, station_id = query.data.split(":", 3)
    await query.answer()

    stations = await _load_system_stations(rail_system)
    station = stations.get(station_id) if stations else None
    if not station:
        await context.bot.send_message(
            update.effective_chat.id,
            "查不到這一站的資料欸，晚點再試試看！",
            reply_to_message_id=query.message.message_id,
        )
        return

    await context.bot.send_message(
        update.effective_chat.id,
        _format_station_text(station),
        reply_to_message_id=query.message.message_id,
    )


def _format_station_text(station: dict) -> str:
    lines = [f"🚇 {station['name']}", "\n📍 出入口資訊！"]

    for exit_item in sorted(station["exits"], key=lambda e: e["ExitID"]):
        # TDX 的 ExitID 有些車站（如台北車站）是空字串，這種名稱本身就帶編號（M4、M8...）了，
        # 所以只有 ExitID 有值時才加在前面，避免多出一個空白
        exit_name = exit_item["ExitName"]["Zh_tw"]
        stair = YES_NO_SYMBOLS[bool(exit_item.get("Stair"))]
        elevator = YES_NO_SYMBOLS[bool(exit_item.get("Elevator"))]
        escalator = ESCALATOR_SYMBOLS.get(exit_item.get("Escalator", 0), "❌")
        lines.append(f"{exit_name}\n樓梯：{stair}｜電梯：{elevator}｜手扶梯：{escalator}\n")

    if station["elevators"]:
        lines.append("\n♿ 無障礙電梯位置")
        # 有些軌道系統（如台中捷運）送來的資料沒有 FloorLevel 欄位，即使 TDX 文件寫是必填
        lines.extend(f"{e.get('FloorLevel', '')} {e['Description']}".strip() for e in station["elevators"])

    if station["toilets"]:
        lines.append("\n🚻 廁所位置")
        lines.extend(f"{t.get('FloorLevel', '')} {t['Description']}".strip() for t in station["toilets"])
    else:
        lines.append("\n🚻 廁所：查無資料")

    # TDX 捷運站設施 API 目前沒有寄物櫃欄位，所以查不到
    lines.append("\n🧳 寄物櫃：TDX 沒有提供這項資料，建議到現場詢問處確認")

    return "\n".join(lines)
