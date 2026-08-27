import functools
import heapq
import time

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

# TDX ODFare 的 FareClass：實測只有 1 能確定是「全票／單程票」，其他代碼（3、4、5、7...）
# 官方文件對照不夠明確，怕標錯票種誤導金額資訊，先只呈現全票
FARE_CLASS_FULL_FARE = 1

# TDX Escalator 欄位：0:沒有,1:雙向,2:出站(往上),3:入站(往下)
ESCALATOR_SYMBOLS = {0: "❌", 1: "↕️", 2: "⬆️", 3: "⬇️"}
YES_NO_SYMBOLS = {True: "⭕", False: "❌"}

# 跨線轉乘的走路時間估計值。TDX 沒有 MRT 月台間轉乘時間的資料
# （StationTransfer API 給的是轉乘 YouBike／公車／停車場），所以用一個保守的固定值，
# 行車時間查詢的結果本來就標成「最少約」。
INTERCHANGE_WALK_SECONDS = 180

_token_cache = {"access_token": None, "expires_at": 0.0}
_station_cache = {}  # rail_system -> {"expires_at": ts, "stations": {station_id: {...}}}
_line_cache = {}  # rail_system -> {"expires_at": ts, "lines": {line_id: {"name": ..., "stations": [(id, name), ...]}}}
_travel_time_cache = {}  # rail_system -> {"expires_at": ts, "segments": {(from_id, to_id): {"run": sec, "stop": sec}}}


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
            {
                "name": item["StationName"]["Zh_tw"],
                "exits": [],
                "elevators": [],
                "toilets": [],
                "drinking_fountains": [],
                "facility_map_urls": [],
            },
        )
        station["exits"].append(item)

    for item in facilities or []:
        station = stations.setdefault(
            item["StationID"],
            {
                "name": item["StationName"]["Zh_tw"],
                "exits": [],
                "elevators": [],
                "toilets": [],
                "drinking_fountains": [],
                "facility_map_urls": [],
            },
        )
        station["elevators"] = item.get("Elevators") or []
        station["toilets"] = item.get("Toilets") or []
        station["drinking_fountains"] = item.get("DrinkingFountains") or []
        station["facility_map_urls"] = item.get("FacilityMapURLs") or []

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


async def _load_system_travel_times(rail_system: str) -> dict | None:
    cached = _travel_time_cache.get(rail_system)
    now = time.time()
    if cached and cached["expires_at"] > now:
        return cached["segments"]

    data = await _tdx_get(f"/v2/Rail/Metro/S2STravelTime/{rail_system}")
    if data is None:
        return None

    # S2STravelTime 是「一條路線一筆、裡面帶相鄰兩站的行駛/停靠秒數」，
    # 攤平成 (起站, 迄站) -> 秒數 的查表，之後照使用者選的路線把中間每一段加起來
    segments = {}
    for line in data:
        for seg in line.get("TravelTimes", []):
            segments[(seg["FromStationID"], seg["ToStationID"])] = {
                "run": seg.get("RunTime", 0),
                "stop": seg.get("StopTime", 0),
            }

    _travel_time_cache[rail_system] = {"expires_at": now + DATA_CACHE_TTL_SECONDS, "segments": segments}
    return segments


def _interchange_groups(lines: dict) -> list:
    # 轉乘站在每條線各有一個 line-prefixed StationID（例如忠孝復興 = BL15／BR10），
    # 用「同名、不同 ID」把同一個實體車站的各月台認出來
    by_name = {}
    for line in lines.values():
        for sid, name in line["stations"]:
            by_name.setdefault(name, set()).add(sid)
    return [sorted(ids) for ids in by_name.values() if len(ids) > 1]


def _build_travel_graph(segments: dict, interchange_groups: list) -> dict:
    # 把整個系統組成一張圖：搭車段（雙向、權重＝行駛＋停靠秒數）＋轉乘段（走路時間用估計值）
    # kind 記著這條邊是「搭車」還是「轉乘」，之後才能拆出各佔多少時間、經過幾次轉乘
    graph = {}

    def add_edge(a, b, seconds, kind):
        graph.setdefault(a, []).append((b, seconds, kind))

    for (from_id, to_id), sec in segments.items():
        weight = sec["run"] + sec["stop"]
        add_edge(from_id, to_id, weight, "ride")
        add_edge(to_id, from_id, weight, "ride")

    for group in interchange_groups:
        for from_id in group:
            for to_id in group:
                if from_id != to_id:
                    add_edge(from_id, to_id, INTERCHANGE_WALK_SECONDS, "transfer")

    return graph


def _shortest_travel(graph: dict, origin_id: str, dest_id: str) -> tuple | None:
    # 一般的 Dijkstra，回傳 (總秒數, 搭車秒數, 轉乘秒數, [轉乘站ID, ...])
    if origin_id == dest_id:
        return (0, 0, 0, [])
    if origin_id not in graph or dest_id not in graph:
        return None

    best = {origin_id: (0, 0, 0)}  # node -> (總秒數, 搭車秒數, 轉乘秒數)
    prev = {}  # node -> (前一站, kind)
    pq = [(0, origin_id)]
    visited = set()

    while pq:
        dist, node = heapq.heappop(pq)
        if node in visited:
            continue
        visited.add(node)
        if node == dest_id:
            break
        ride_so_far, transfer_so_far = best[node][1], best[node][2]
        for neighbor, weight, kind in graph.get(node, []):
            if neighbor in visited:
                continue
            new_dist = dist + weight
            if neighbor not in best or new_dist < best[neighbor][0]:
                best[neighbor] = (
                    new_dist,
                    ride_so_far + (weight if kind == "ride" else 0),
                    transfer_so_far + (weight if kind == "transfer" else 0),
                )
                prev[neighbor] = (node, kind)
                heapq.heappush(pq, (new_dist, neighbor))

    if dest_id not in best:
        return None

    transfer_nodes = []
    cur = dest_id
    while cur in prev:
        parent, kind = prev[cur]
        if kind == "transfer":
            transfer_nodes.append(parent)
        cur = parent
    transfer_nodes.reverse()

    total, ride, transfer = best[dest_id]
    return (total, ride, transfer, transfer_nodes)


def _minutes(seconds: int) -> int:
    return max(1, round(seconds / 60))


def _format_travel_time_text(
    system_name: str, origin_name: str, dest_name: str, id_to_name: dict, result: tuple
) -> str:
    total, ride, transfer, transfer_nodes = result

    header = f"🚇 {origin_name} → {dest_name}"

    if transfer_nodes:
        names = "、".join(id_to_name.get(n, n) for n in transfer_nodes)
        body = "\n".join(
            [
                f"🕐 最少約 {_minutes(total)} 分鐘"
                f"（車上約 {_minutes(ride)} 分 + 轉乘步行約 {_minutes(transfer)} 分）",
                f"🔁 轉乘 {len(transfer_nodes)} 次：{names}",
            ]
        )
    else:
        body = f"🕐 最少約 {_minutes(total)} 分鐘"

    # 三段之間各空一行
    return "\n\n".join([header, body, "＊不含月台候車時間，實際會再久一些"])


async def _fetch_od_fare(rail_system: str, origin_id: str, dest_id: str) -> dict | None:
    # ODFare 本身就是任兩站直接配對好的價目表，不用逐站累加車資（捷運票價也不是逐站相加算的）
    results = await _tdx_get(
        f"/v2/Rail/Metro/ODFare/{rail_system}",
        **{"$filter": f"OriginStationID eq '{origin_id}' and DestinationStationID eq '{dest_id}'"},
    )
    return results[0] if results else None


async def mrt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = chunk(list(RAIL_SYSTEMS.items()), SYSTEM_BUTTONS_PER_ROW)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(name, callback_data=f"mrt:system:{code}") for code, name in row] for row in rows]
    )
    await update.message.reply_text("要查哪個軌道系統的車站出入口呢？", reply_markup=keyboard)


@dismiss_menu
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


@dismiss_menu
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


@dismiss_menu
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

    if station["drinking_fountains"]:
        lines.append("\n🚰 飲水機位置")
        lines.extend(
            f"{d.get('FloorLevel', '')} {d['Description']}".strip() for d in station["drinking_fountains"]
        )
    else:
        lines.append("\n🚰 飲水機：查無資料")

    # 有些軌道系統（如臺北捷運）沒有把廁所/飲水機的詳細位置列給 TDX，只給了一份車站資訊圖，
    # 查無資料時附上圖讓使用者自己找
    if (not station["toilets"] or not station["drinking_fountains"]) and station["facility_map_urls"]:
        lines.append("\n🗺 查無詳細位置時，可以參考車站資訊圖")
        lines.extend(f"{m['MapName']['Zh_tw']}：{m['MapURL']}" for m in station["facility_map_urls"])

    return "\n".join(lines)


async def mrtfare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = chunk(list(RAIL_SYSTEMS.items()), SYSTEM_BUTTONS_PER_ROW)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(name, callback_data=f"fare:system:{code}") for code, name in row] for row in rows]
    )
    await update.message.reply_text("要查哪個軌道系統的票價呢？", reply_markup=keyboard)


@dismiss_menu
async def handle_fare_system_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                InlineKeyboardButton(info["name"], callback_data=f"fare:origin_line:{rail_system}:{line_id}")
                for line_id, info in row
            ]
            for row in rows
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        f"{system_name}要查「起站」是哪條路線呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


@dismiss_menu
async def handle_fare_origin_line_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            [
                InlineKeyboardButton(name, callback_data=f"fare:origin_station:{rail_system}:{sid}")
                for sid, name in row
            ]
            for row in rows
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        f"{line['name']}要查哪一站當「起站」呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


@dismiss_menu
async def handle_fare_origin_station_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, rail_system, origin_id = query.data.split(":", 3)
    await query.answer()

    lines = await _load_system_lines(rail_system)
    if not lines:
        await context.bot.send_message(
            update.effective_chat.id,
            "查不到路線資料欸，晚點再試試看！",
            reply_to_message_id=query.message.message_id,
        )
        return

    sorted_lines = sorted(lines.items(), key=lambda kv: kv[0])
    rows = chunk(sorted_lines, LINE_BUTTONS_PER_ROW)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    info["name"], callback_data=f"fare:dest_line:{rail_system}:{origin_id}:{line_id}"
                )
                for line_id, info in row
            ]
            for row in rows
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        "要查「到站」是哪條路線呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


@dismiss_menu
async def handle_fare_dest_line_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, rail_system, origin_id, line_id = query.data.split(":", 4)
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
            [
                InlineKeyboardButton(name, callback_data=f"fare:dest_station:{rail_system}:{origin_id}:{sid}")
                for sid, name in row
            ]
            for row in rows
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        f"{line['name']}要查哪一站當「到站」呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


@dismiss_menu
async def handle_fare_dest_station_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, rail_system, origin_id, dest_id = query.data.split(":", 4)
    await query.answer()

    fare = await _fetch_od_fare(rail_system, origin_id, dest_id)
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


def _format_fare_text(fare: dict) -> str:
    origin_name = fare["OriginStationName"]["Zh_tw"]
    dest_name = fare["DestinationStationName"]["Zh_tw"]
    full_fare = next((f["Price"] for f in fare["Fares"] if f["FareClass"] == FARE_CLASS_FULL_FARE), None)
    distance = fare.get("TravelDistance")

    lines = [f"🚇 {origin_name} → {dest_name}"]
    if full_fare is not None:
        lines.append(f"💰 全票票價：NT$ {full_fare}")
    else:
        lines.append("💰 查無全票票價資料")
    if distance:
        lines.append(f"📏 里程：約 {distance} 公里")

    return "\n".join(lines)


# 行車時間查詢：跨線（同一個捷運系統內）用最短路徑算。流程比照 /mrtfare：
# 系統 → 起站路線 → 起站 → 迄站路線 → 迄站。搭車段用 S2STravelTime，轉乘站用「同名不同 ID」認出來、
# 走路時間用固定估計值（TDX 沒有月台間轉乘時間），也沒有候車資料，所以結果標成「最少約 X 分」。
def _all_station_names(lines: dict) -> dict:
    return {sid: name for line in lines.values() for sid, name in line["stations"]}


async def _mrttime_no_data(context, chat_id, message_id):
    await context.bot.send_message(
        chat_id,
        "查不到這兩站之間的行車時間資料欸，晚點再試試看！",
        reply_to_message_id=message_id,
    )


async def mrttime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = chunk(list(RAIL_SYSTEMS.items()), SYSTEM_BUTTONS_PER_ROW)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(name, callback_data=f"mrttime:system:{code}") for code, name in row] for row in rows]
    )
    await update.message.reply_text("要查哪個軌道系統的行車時間呢？", reply_markup=keyboard)


@dismiss_menu
async def handle_mrttime_system_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                InlineKeyboardButton(info["name"], callback_data=f"mrttime:oline:{rail_system}:{line_id}")
                for line_id, info in row
            ]
            for row in rows
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        f"{system_name}要查「起站」是哪條路線呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


@dismiss_menu
async def handle_mrttime_origin_line_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            [
                InlineKeyboardButton(name, callback_data=f"mrttime:ostn:{rail_system}:{sid}")
                for sid, name in row
            ]
            for row in rows
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        f"{line['name']}要從哪一站出發呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


@dismiss_menu
async def handle_mrttime_origin_station_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, rail_system, origin_id = query.data.split(":", 3)
    await query.answer()

    lines = await _load_system_lines(rail_system)
    if not lines:
        await context.bot.send_message(
            update.effective_chat.id,
            "查不到路線資料欸，晚點再試試看！",
            reply_to_message_id=query.message.message_id,
        )
        return

    sorted_lines = sorted(lines.items(), key=lambda kv: kv[0])
    rows = chunk(sorted_lines, LINE_BUTTONS_PER_ROW)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    info["name"], callback_data=f"mrttime:dline:{rail_system}:{origin_id}:{line_id}"
                )
                for line_id, info in row
            ]
            for row in rows
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        "要查「迄站」是哪條路線呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


@dismiss_menu
async def handle_mrttime_dest_line_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, rail_system, origin_id, line_id = query.data.split(":", 4)
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

    dest_stations = [(sid, name) for sid, name in line["stations"] if sid != origin_id]
    rows = chunk(dest_stations, STATION_BUTTONS_PER_ROW)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(name, callback_data=f"mrttime:dstn:{rail_system}:{origin_id}:{sid}")
                for sid, name in row
            ]
            for row in rows
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        f"{line['name']}要到哪一站呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


@dismiss_menu
async def handle_mrttime_dest_station_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, rail_system, origin_id, dest_id = query.data.split(":", 4)
    await query.answer()
    chat_id, message_id = update.effective_chat.id, query.message.message_id
    system_name = RAIL_SYSTEMS.get(rail_system, rail_system)

    lines = await _load_system_lines(rail_system)
    segments = await _load_system_travel_times(rail_system)
    if not lines or segments is None:
        await _mrttime_no_data(context, chat_id, message_id)
        return

    graph = _build_travel_graph(segments, _interchange_groups(lines))
    result = _shortest_travel(graph, origin_id, dest_id)
    if result is None:
        await _mrttime_no_data(context, chat_id, message_id)
        return

    id_to_name = _all_station_names(lines)
    await context.bot.send_message(
        chat_id,
        _format_travel_time_text(
            system_name, id_to_name.get(origin_id, origin_id), id_to_name.get(dest_id, dest_id), id_to_name, result
        ),
        reply_to_message_id=message_id,
    )
