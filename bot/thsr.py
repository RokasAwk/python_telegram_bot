import functools
import time
from datetime import date, datetime

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .config import TDX_API_BASE_URL, TDX_AUTH_URL, TDX_CLIENT_ID, TDX_CLIENT_SECRET, logger


def dismiss_menu(handler):
    """使用者點過選單按鈕後，就地把那則訊息的按鈕銷毀，避免又回頭點到同一層的舊選單。"""

    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query is not None:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except TelegramError:
                # 訊息太舊或已被改過都不影響後續查詢，忽略就好
                pass
        return await handler(update, context)

    return wrapper


STATION_BUTTONS_PER_ROW = 4

# 車站資料變動不頻繁，快取一段時間避免每次點站名都重打 TDX API
DATA_CACHE_TTL_SECONDS = 3600

# TDX THSR ODFare 的 CabinClass：1 標準車廂、2 商務車廂。3 目前無法從文件確定對應票種，先不顯示避免標錯
CABIN_CLASS_STANDARD = 1
CABIN_CLASS_BUSINESS = 2

# TDX ODFare 的 FareClass：實測只有 1 能確定是「全票」，其他代碼官方文件對照不夠明確，先只呈現全票
FARE_CLASS_FULL_FARE = 1

_token_cache = {"access_token": None, "expires_at": 0.0}
_station_cache = {"expires_at": 0.0, "stations": {}}


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


async def _tdx_get(path: str, **params) -> list | None:
    token = await _get_access_token()
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    query = {"$format": "JSON", **params}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{TDX_API_BASE_URL}{path}", params=query, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        logger.exception("查詢 TDX API 失敗：%s", path)
        return None


async def _load_stations() -> dict | None:
    now = time.time()
    if _station_cache["stations"] and _station_cache["expires_at"] > now:
        return _station_cache["stations"]

    data = await _tdx_get("/v2/Rail/THSR/Station")
    if data is None:
        return None

    # StationID 由北到南遞增（南港 0990 ... 左營 1070），排序後正好是路線順序
    stations = {item["StationID"]: item["StationName"]["Zh_tw"] for item in data}
    _station_cache["stations"] = stations
    _station_cache["expires_at"] = now + DATA_CACHE_TTL_SECONDS
    return stations


async def _fetch_daily_timetable(origin_id: str, dest_id: str, train_date: str) -> list | None:
    return await _tdx_get(f"/v2/Rail/THSR/DailyTimetable/OD/{origin_id}/to/{dest_id}/{train_date}")


async def _fetch_od_fare(origin_id: str, dest_id: str) -> dict | None:
    results = await _tdx_get(f"/v2/Rail/THSR/ODFare/{origin_id}/to/{dest_id}")
    return results[0] if results else None


def _station_keyboard(stations: dict, callback_prefix: str) -> InlineKeyboardMarkup:
    sorted_stations = sorted(stations.items())
    rows = chunk(sorted_stations, STATION_BUTTONS_PER_ROW)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(name, callback_data=f"{callback_prefix}:{sid}") for sid, name in row]
            for row in rows
        ]
    )


def _duration_minutes(departure: str, arrival: str) -> int:
    # API 只給起訖時間點（HH:MM），沒有現成的車程欄位，自己相減算出來
    dep = datetime.strptime(departure, "%H:%M")
    arr = datetime.strptime(arrival, "%H:%M")
    return int((arr - dep).total_seconds() // 60)


def _format_duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    return f"{hours}小時{mins}分" if hours else f"{mins}分"


def _format_timetable_text(origin_name: str, dest_name: str, train_date: str, trains: list) -> str:
    header = f"🚄 {origin_name} → {dest_name}（{train_date}）"
    if not trains:
        return f"{header}\n查無班次資料"

    sorted_trains = sorted(trains, key=lambda t: t["OriginStopTime"]["DepartureTime"])
    durations = [
        _duration_minutes(t["OriginStopTime"]["DepartureTime"], t["DestinationStopTime"]["ArrivalTime"])
        for t in sorted_trains
    ]
    fastest_minutes = min(durations)

    lines = [header, ""]
    for train, minutes in zip(sorted_trains, durations):
        train_no = train["DailyTrainInfo"]["TrainNo"]
        departure = train["OriginStopTime"]["DepartureTime"]
        arrival = train["DestinationStopTime"]["ArrivalTime"]
        badge = " ⚡" if minutes == fastest_minutes else ""
        lines.append(f"🚆 班次 {train_no}{badge}")
        lines.append(f"{departure} → {arrival}｜{_format_duration(minutes)}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _format_fare_text(fare: dict) -> str:
    origin_name = fare["OriginStationName"]["Zh_tw"]
    dest_name = fare["DestinationStationName"]["Zh_tw"]
    standard_fare = next(
        (
            f["Price"]
            for f in fare["Fares"]
            if f["FareClass"] == FARE_CLASS_FULL_FARE and f["CabinClass"] == CABIN_CLASS_STANDARD
        ),
        None,
    )
    business_fare = next(
        (
            f["Price"]
            for f in fare["Fares"]
            if f["FareClass"] == FARE_CLASS_FULL_FARE and f["CabinClass"] == CABIN_CLASS_BUSINESS
        ),
        None,
    )

    lines = [f"🚄 {origin_name} → {dest_name}"]
    if standard_fare is not None:
        lines.append(f"💰 標準車廂全票：NT$ {standard_fare}")
    else:
        lines.append("💰 查無標準車廂全票票價資料")
    if business_fare is not None:
        lines.append(f"💼 商務車廂全票：NT$ {business_fare}")

    return "\n".join(lines)


async def _reply_no_credentials(message):
    await message.reply_text(
        "還沒設定 TDX_CLIENT_ID / TDX_CLIENT_SECRET，小狼查不到高鐵資料，跟壽司狼哥哥說一下吧！"
    )


async def thsrtime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (TDX_CLIENT_ID and TDX_CLIENT_SECRET):
        await _reply_no_credentials(update.message)
        return

    stations = await _load_stations()
    if not stations:
        await update.message.reply_text("查不到高鐵車站資料欸，晚點再試試看！")
        return

    await update.message.reply_text(
        "要查哪一站出發的時刻表呢？",
        reply_markup=_station_keyboard(stations, "thsrtime:origin"),
    )


@dismiss_menu
async def handle_thsrtime_origin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    origin_id = query.data.split(":", 2)[2]
    await query.answer()

    stations = await _load_stations()
    if not stations:
        await context.bot.send_message(
            update.effective_chat.id,
            "查不到高鐵車站資料欸，晚點再試試看！",
            reply_to_message_id=query.message.message_id,
        )
        return

    dest_stations = {sid: name for sid, name in stations.items() if sid != origin_id}
    await context.bot.send_message(
        update.effective_chat.id,
        f"{stations[origin_id]}要查到哪一站呢？",
        reply_markup=_station_keyboard(dest_stations, f"thsrtime:dest:{origin_id}"),
        reply_to_message_id=query.message.message_id,
    )


@dismiss_menu
async def handle_thsrtime_dest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, origin_id, dest_id = query.data.split(":", 3)
    await query.answer()

    stations = await _load_stations()
    if not stations:
        await context.bot.send_message(
            update.effective_chat.id,
            "查不到高鐵車站資料欸，晚點再試試看！",
            reply_to_message_id=query.message.message_id,
        )
        return

    train_date = date.today().isoformat()
    trains = await _fetch_daily_timetable(origin_id, dest_id, train_date)
    if trains is None:
        await context.bot.send_message(
            update.effective_chat.id,
            "查不到這兩站之間的時刻表欸，晚點再試試看！",
            reply_to_message_id=query.message.message_id,
        )
        return

    await context.bot.send_message(
        update.effective_chat.id,
        _format_timetable_text(stations[origin_id], stations[dest_id], train_date, trains),
        reply_to_message_id=query.message.message_id,
    )


async def thsrfare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (TDX_CLIENT_ID and TDX_CLIENT_SECRET):
        await _reply_no_credentials(update.message)
        return

    stations = await _load_stations()
    if not stations:
        await update.message.reply_text("查不到高鐵車站資料欸，晚點再試試看！")
        return

    await update.message.reply_text(
        "要查哪一站出發的票價呢？",
        reply_markup=_station_keyboard(stations, "thsrfare:origin"),
    )


@dismiss_menu
async def handle_thsrfare_origin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    origin_id = query.data.split(":", 2)[2]
    await query.answer()

    stations = await _load_stations()
    if not stations:
        await context.bot.send_message(
            update.effective_chat.id,
            "查不到高鐵車站資料欸，晚點再試試看！",
            reply_to_message_id=query.message.message_id,
        )
        return

    dest_stations = {sid: name for sid, name in stations.items() if sid != origin_id}
    await context.bot.send_message(
        update.effective_chat.id,
        f"{stations[origin_id]}要查到哪一站的票價呢？",
        reply_markup=_station_keyboard(dest_stations, f"thsrfare:dest:{origin_id}"),
        reply_to_message_id=query.message.message_id,
    )


@dismiss_menu
async def handle_thsrfare_dest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, origin_id, dest_id = query.data.split(":", 3)
    await query.answer()

    fare = await _fetch_od_fare(origin_id, dest_id)
    if fare is None:
        await context.bot.send_message(
            update.effective_chat.id,
            "查不到這兩站之間的票價資料欸，晚點再試試看！",
            reply_to_message_id=query.message.message_id,
        )
        return

    await context.bot.send_message(
        update.effective_chat.id,
        _format_fare_text(fare),
        reply_to_message_id=query.message.message_id,
    )
