import ssl
from datetime import datetime, timedelta

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .config import CWA_API_KEY, CWA_DATASTORE_BASE_URL, logger

# 氣象署憑證鏈（TWCA Secure SSL Certification Authority）缺 Subject Key Identifier
# 擴充欄位，Python 3.13+ 預設開啟的 VERIFY_X509_STRICT 會判定驗證失敗，
# 但憑證鏈本身是有效的（openssl s_client 驗證得過），所以只針對氣象署連線關掉這個嚴格旗標
_CWA_SSL_CONTEXT = httpx.create_ssl_context()
_CWA_SSL_CONTEXT.verify_flags &= ~ssl.VERIFY_X509_STRICT

# 中央氣象署已下架縣市層級的「一週縣市天氣預報」（F-C0032-005），一週資料現在併進
# 鄉鎮天氣預報（F-D0047 系列），每個縣市各自一組 dataset id，且是以鄉鎮為單位。
# 這裡幫每個縣市挑一個代表行政區（多為縣市政府所在地）來查詢。
# city -> (dataset_id, 代表鄉鎮)
COUNTY_WEEKLY_DATASETS = {
    "基隆市": ("F-D0047-051", "中正區"),
    "臺北市": ("F-D0047-063", "信義區"),
    "新北市": ("F-D0047-071", "板橋區"),
    "桃園市": ("F-D0047-007", "桃園區"),
    "新竹市": ("F-D0047-055", "東區"),
    "新竹縣": ("F-D0047-011", "竹北市"),
    "苗栗縣": ("F-D0047-015", "苗栗市"),
    "臺中市": ("F-D0047-075", "西屯區"),
    "彰化縣": ("F-D0047-019", "彰化市"),
    "南投縣": ("F-D0047-023", "南投市"),
    "雲林縣": ("F-D0047-027", "斗六市"),
    "嘉義市": ("F-D0047-059", "東區"),
    "嘉義縣": ("F-D0047-031", "太保市"),
    "臺南市": ("F-D0047-079", "安平區"),
    "高雄市": ("F-D0047-067", "苓雅區"),
    "屏東縣": ("F-D0047-035", "屏東市"),
    "宜蘭縣": ("F-D0047-003", "宜蘭市"),
    "花蓮縣": ("F-D0047-043", "花蓮市"),
    "臺東縣": ("F-D0047-039", "臺東市"),
    "澎湖縣": ("F-D0047-047", "馬公市"),
    "金門縣": ("F-D0047-087", "金城鎮"),
    "連江縣": ("F-D0047-083", "南竿鄉"),
}
TAIWAN_CITIES = list(COUNTY_WEEKLY_DATASETS)
CITY_BUTTONS_PER_ROW = 3

# 未來3天資料集跟一週資料集是同一個縣市的成對 id，3天永遠是週資料 id 減 2
# （例：臺北市一週=F-D0047-063，未來3天=F-D0047-061），已對全部22縣市實測驗證過
THREE_DAY_DATASETS = {
    city: (f"F-D0047-{int(weekly_id.split('-')[2]) - 2:03d}", township)
    for city, (weekly_id, township) in COUNTY_WEEKLY_DATASETS.items()
}

DAILY_FORECAST_DATASET_ID = "F-C0032-001"

WEEKDAY_NAMES = "一二三四五六日"

PERIOD_LABELS = {"today": "☀️ 當日天氣", "3day": "🌤 三天天氣", "week": "🗓 一週天氣"}


def chunk(items, size):
    return [items[i : i + size] for i in range(0, len(items), size)]


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = chunk(TAIWAN_CITIES, CITY_BUTTONS_PER_ROW)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(city, callback_data=f"weather:city:{city}") for city in row] for row in rows]
    )
    user = update.effective_user
    await update.message.reply_text(
        f"[{user.first_name}](tg://user?id={user.id}) 你想問小狼哪裡的天氣呢？",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def handle_weather_city_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    city = query.data.split(":", 2)[2]
    await query.answer()
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(PERIOD_LABELS["today"], callback_data=f"weather:period:today:{city}"),
                InlineKeyboardButton(PERIOD_LABELS["3day"], callback_data=f"weather:period:3day:{city}"),
                InlineKeyboardButton(PERIOD_LABELS["week"], callback_data=f"weather:period:week:{city}"),
            ]
        ]
    )
    await context.bot.send_message(
        update.effective_chat.id,
        f"{city}要看當日天氣還是一週天氣呢？",
        reply_markup=keyboard,
        reply_to_message_id=query.message.message_id,
    )


async def handle_weather_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, period, city = query.data.split(":", 3)
    await query.answer()
    if period == "week":
        text = await fetch_weekly_weather_text(city)
    elif period == "3day":
        text = await fetch_3day_weather_text(city)
    else:
        text = await fetch_daily_weather_text(city)
    await context.bot.send_message(
        update.effective_chat.id,
        text,
        reply_to_message_id=query.message.message_id,
    )


async def fetch_daily_weather_text(city: str) -> str:
    if city not in COUNTY_WEEKLY_DATASETS:
        return f"找不到「{city}」的天氣資料欸"

    if not CWA_API_KEY:
        return "還沒設定 CWA_API_KEY，小狼查不到天氣，跟壽司狼哥哥說一下吧！"

    params = {
        "Authorization": CWA_API_KEY,
        "locationName": city,
        "elementName": "Wx,MaxT,MinT,PoP",
    }
    try:
        async with httpx.AsyncClient(timeout=10, verify=_CWA_SSL_CONTEXT) as client:
            resp = await client.get(f"{CWA_DATASTORE_BASE_URL}/{DAILY_FORECAST_DATASET_ID}", params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        logger.exception("查詢中央氣象署 API 失敗")
        return "氣象署那邊查不到資料欸，晚點再試試看！"

    locations = data.get("records", {}).get("location", [])
    if not locations:
        return f"找不到「{city}」的天氣資料欸"

    elements = {el["elementName"]: el["time"] for el in locations[0]["weatherElement"]}
    wx_periods = elements.get("Wx", [])
    if not wx_periods:
        return f"找不到「{city}」的天氣資料欸"

    lines = [f"📍 {city}天氣預報"]
    for i in range(min(2, len(wx_periods))):
        wx = wx_periods[i]
        start = wx["startTime"][5:16].replace("-", "/")
        end = wx["endTime"][5:16].replace("-", "/")
        condition = wx["parameter"]["parameterName"]
        min_t = elements["MinT"][i]["parameter"]["parameterName"]
        max_t = elements["MaxT"][i]["parameter"]["parameterName"]
        pop = elements["PoP"][i]["parameter"]["parameterName"]
        lines.append(
            f"\n🕐 {start} - {end}\n"
            f"☁️ {condition}\n"
            f"🌡️ {min_t}°C - {max_t}°C\n"
            f"☔ 降雨機率 {pop}%"
        )
    return "\n".join(lines)


def _half_day_bucket(start: datetime):
    # F-D0047「未來3天」是逐3小時分段，跨半夜的段（00:00~06:00）要算進前一晚的「晚上」，
    # 不能自己獨立變成新的一天
    if start.hour >= 18:
        return start.date(), "晚上"
    if start.hour < 6:
        return start.date() - timedelta(days=1), "晚上"
    return start.date(), "白天"


async def fetch_3day_weather_text(city: str) -> str:
    dataset = THREE_DAY_DATASETS.get(city)
    if not dataset:
        return f"找不到「{city}」的天氣資料欸"
    dataset_id, township = dataset

    if not CWA_API_KEY:
        return "還沒設定 CWA_API_KEY，小狼查不到天氣，跟壽司狼哥哥說一下吧！"

    params = {
        "Authorization": CWA_API_KEY,
        "LocationName": township,
        "ElementName": "天氣現象,溫度,3小時降雨機率",
    }
    try:
        async with httpx.AsyncClient(timeout=10, verify=_CWA_SSL_CONTEXT) as client:
            resp = await client.get(f"{CWA_DATASTORE_BASE_URL}/{dataset_id}", params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        logger.exception("查詢中央氣象署 API 失敗")
        return "氣象署那邊查不到資料欸，晚點再試試看！"

    locations = data.get("records", {}).get("Locations", [{}])[0].get("Location", [])
    if not locations:
        return f"找不到「{city}」的天氣資料欸"

    elements = {el["ElementName"]: el["Time"] for el in locations[0]["WeatherElement"]}
    wx_periods = elements.get("天氣現象", [])
    if not wx_periods:
        return f"找不到「{city}」的天氣資料欸"

    # 「溫度」是逐時單點資料，「3小時降雨機率」跟「天氣現象」一樣是逐3小時分段，
    # 用 StartTime 對照才能湊出同一段時間的溫度／降雨機率
    temp_by_time = {
        t["DataTime"]: int(t["ElementValue"][0]["Temperature"]) for t in elements.get("溫度", [])
    }
    pop_by_start = {
        p["StartTime"]: p["ElementValue"][0]["ProbabilityOfPrecipitation"]
        for p in elements.get("3小時降雨機率", [])
    }

    buckets = {}
    order = []
    for wx in wx_periods:
        start = datetime.fromisoformat(wx["StartTime"])
        key = _half_day_bucket(start)
        if key not in buckets:
            buckets[key] = {"conditions": [], "pops": [], "temps": []}
            order.append(key)

        buckets[key]["conditions"].append(wx["ElementValue"][0]["Weather"])

        pop = pop_by_start.get(wx["StartTime"])
        buckets[key]["pops"].append(int(pop) if pop and pop != "-" else None)

        temp = temp_by_time.get(wx["StartTime"])
        if temp is not None:
            buckets[key]["temps"].append(temp)

    lines = [f"📍 {city}（{township}）未來三天天氣預報"]
    for bucket_date, half in order[:6]:
        info = buckets[(bucket_date, half)]
        pops_present = [p for p in info["pops"] if p is not None]
        if pops_present:
            worst_idx = info["pops"].index(max(pops_present))
            condition = info["conditions"][worst_idx]
            pop_text = f"{max(pops_present)}%"
        else:
            condition = info["conditions"][0]
            pop_text = "資料未提供"
        temp_text = (
            f"{min(info['temps'])}°C - {max(info['temps'])}°C" if info["temps"] else "資料未提供"
        )
        weekday = WEEKDAY_NAMES[bucket_date.weekday()]
        lines.append(
            f"\n{bucket_date.strftime('%m/%d')}（週{weekday}）{half}\n"
            f"☁️ {condition}\n"
            f"🌡️ {temp_text}\n"
            f"☔ 降雨機率 {pop_text}"
        )
    return "\n".join(lines)


async def fetch_weekly_weather_text(city: str) -> str:
    dataset = COUNTY_WEEKLY_DATASETS.get(city)
    if not dataset:
        return f"找不到「{city}」的天氣資料欸"
    dataset_id, township = dataset

    if not CWA_API_KEY:
        return "還沒設定 CWA_API_KEY，小狼查不到天氣，跟壽司狼哥哥說一下吧！"

    params = {
        "Authorization": CWA_API_KEY,
        "LocationName": township,
        "ElementName": "天氣現象,最高溫度,最低溫度,12小時降雨機率",
    }
    try:
        async with httpx.AsyncClient(timeout=10, verify=_CWA_SSL_CONTEXT) as client:
            resp = await client.get(f"{CWA_DATASTORE_BASE_URL}/{dataset_id}", params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        logger.exception("查詢中央氣象署 API 失敗")
        return "氣象署那邊查不到資料欸，晚點再試試看！"

    locations = data.get("records", {}).get("Locations", [{}])[0].get("Location", [])
    if not locations:
        return f"找不到「{city}」的天氣資料欸"

    elements = {el["ElementName"]: el["Time"] for el in locations[0]["WeatherElement"]}
    wx_periods = elements.get("天氣現象", [])
    if not wx_periods:
        return f"找不到「{city}」的天氣資料欸"

    lines = [f"📍 {city}（{township}）一週天氣預報"]
    for i, wx in enumerate(wx_periods):
        start = datetime.fromisoformat(wx["StartTime"])
        date_str = start.strftime("%m/%d")
        weekday = WEEKDAY_NAMES[start.weekday()]
        period_label = "白天" if start.hour < 18 else "晚上"
        condition = wx["ElementValue"][0]["Weather"]
        min_t = elements["最低溫度"][i]["ElementValue"][0]["MinTemperature"]
        max_t = elements["最高溫度"][i]["ElementValue"][0]["MaxTemperature"]
        pop = elements["12小時降雨機率"][i]["ElementValue"][0]["ProbabilityOfPrecipitation"]
        pop_text = f"{pop}%" if pop != "-" else "資料未提供"
        lines.append(
            f"\n{date_str}（週{weekday}）{period_label}\n"
            f"☁️ {condition}\n"
            f"🌡️ {min_t}°C - {max_t}°C\n"
            f"☔ 降雨機率 {pop_text}"
        )
    return "\n".join(lines)
