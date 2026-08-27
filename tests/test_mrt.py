from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import bot.mrt as mrt_module
from bot.mrt import (
    _build_travel_graph,
    _fetch_od_fare,
    _format_fare_text,
    _format_station_text,
    _format_travel_time_text,
    _get_access_token,
    _interchange_groups,
    _load_system_lines,
    _load_system_stations,
    _load_system_travel_times,
    _shortest_travel,
    _tdx_get,
    chunk,
    handle_fare_dest_line_callback,
    handle_fare_dest_station_callback,
    handle_fare_origin_line_callback,
    handle_fare_origin_station_callback,
    handle_fare_system_callback,
    handle_mrt_line_callback,
    handle_mrt_station_callback,
    handle_mrt_system_callback,
    handle_mrttime_dest_line_callback,
    handle_mrttime_dest_station_callback,
    handle_mrttime_origin_line_callback,
    handle_mrttime_origin_station_callback,
    handle_mrttime_system_callback,
    mrt,
    mrtfare,
    mrttime,
)


@pytest.fixture(autouse=True)
def reset_mrt_module_caches():
    """mrt.py 用 module-level dict 做 cache，測試之間要清乾淨避免互相汙染。"""
    mrt_module._token_cache["access_token"] = None
    mrt_module._token_cache["expires_at"] = 0.0
    mrt_module._station_cache.clear()
    mrt_module._line_cache.clear()
    mrt_module._travel_time_cache.clear()
    yield
    mrt_module._token_cache["access_token"] = None
    mrt_module._token_cache["expires_at"] = 0.0
    mrt_module._station_cache.clear()
    mrt_module._line_cache.clear()
    mrt_module._travel_time_cache.clear()


class FakeResponse:
    def __init__(self, json_data, raise_error=False):
        self._json_data = json_data
        self._raise_error = raise_error

    def raise_for_status(self):
        if self._raise_error:
            request = httpx.Request("GET", "https://example.test")
            raise httpx.HTTPStatusError("boom", request=request, response=httpx.Response(500, request=request))

    def json(self):
        return self._json_data


@pytest.fixture
def mock_async_client(mocker):
    client = AsyncMock()
    client_cls = MagicMock(
        return_value=MagicMock(__aenter__=AsyncMock(return_value=client), __aexit__=AsyncMock(return_value=False))
    )
    mocker.patch("bot.mrt.httpx.AsyncClient", client_cls)
    return client


def test_chunk_splits_into_fixed_size_groups():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunk_with_empty_list():
    assert chunk([], 3) == []


# ---- _get_access_token ----------------------------------------------------


async def test_get_access_token_returns_none_without_credentials(mocker):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", None)
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", None)

    assert await _get_access_token() is None


async def test_get_access_token_fetches_and_caches_new_token(mocker, mock_async_client):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", "id")
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", "secret")
    mock_async_client.post.return_value = FakeResponse({"access_token": "tok123", "expires_in": 3600})

    token = await _get_access_token()

    assert token == "tok123"
    assert mrt_module._token_cache["access_token"] == "tok123"
    mock_async_client.post.assert_awaited_once()


async def test_get_access_token_reuses_cached_token_without_new_request(mocker, mock_async_client):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", "id")
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", "secret")
    mrt_module._token_cache["access_token"] = "cached-tok"
    mrt_module._token_cache["expires_at"] = mrt_module.time.time() + 100

    token = await _get_access_token()

    assert token == "cached-tok"
    mock_async_client.post.assert_not_called()


async def test_get_access_token_returns_none_on_http_error(mocker, mock_async_client):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", "id")
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", "secret")
    mock_async_client.post.return_value = FakeResponse({}, raise_error=True)

    assert await _get_access_token() is None


# ---- _tdx_get ---------------------------------------------------------------


async def test_tdx_get_returns_none_when_no_token(mocker):
    mocker.patch("bot.mrt._get_access_token", new=AsyncMock(return_value=None))

    assert await _tdx_get("/some/path") is None


async def test_tdx_get_returns_json_on_success(mocker, mock_async_client):
    mocker.patch("bot.mrt._get_access_token", new=AsyncMock(return_value="tok"))
    mock_async_client.get.return_value = FakeResponse([{"a": 1}])

    result = await _tdx_get("/some/path")

    assert result == [{"a": 1}]


async def test_tdx_get_returns_none_on_http_error(mocker, mock_async_client):
    mocker.patch("bot.mrt._get_access_token", new=AsyncMock(return_value="tok"))
    mock_async_client.get.return_value = FakeResponse({}, raise_error=True)

    assert await _tdx_get("/some/path") is None


# ---- _load_system_stations ---------------------------------------------------


async def test_load_system_stations_merges_exits_and_facilities(mocker):
    exits = [
        {"StationID": "S1", "StationName": {"Zh_tw": "測試站"}, "ExitID": "1", "ExitName": {"Zh_tw": "1號出口"}},
    ]
    facilities = [
        {
            "StationID": "S1",
            "StationName": {"Zh_tw": "測試站"},
            "Elevators": [{"Description": "電梯A"}],
            "Toilets": [{"Description": "廁所A"}],
            "DrinkingFountains": [{"Description": "飲水機A"}],
            "FacilityMapURLs": [{"MapName": {"Zh_tw": "測試站資訊圖"}, "MapURL": "https://example.test/map.pdf"}],
        }
    ]
    mocker.patch("bot.mrt._tdx_get", new=AsyncMock(side_effect=[exits, facilities]))

    stations = await _load_system_stations("TRTC")

    assert stations["S1"]["name"] == "測試站"
    assert len(stations["S1"]["exits"]) == 1
    assert stations["S1"]["elevators"] == [{"Description": "電梯A"}]
    assert stations["S1"]["toilets"] == [{"Description": "廁所A"}]
    assert stations["S1"]["drinking_fountains"] == [{"Description": "飲水機A"}]
    assert stations["S1"]["facility_map_urls"] == [
        {"MapName": {"Zh_tw": "測試站資訊圖"}, "MapURL": "https://example.test/map.pdf"}
    ]


async def test_load_system_stations_returns_none_when_exits_missing(mocker):
    mocker.patch("bot.mrt._tdx_get", new=AsyncMock(return_value=None))

    assert await _load_system_stations("TRTC") is None


async def test_load_system_stations_keeps_exits_when_facilities_unavailable(mocker):
    exits = [{"StationID": "S1", "StationName": {"Zh_tw": "測試站"}, "ExitID": "1", "ExitName": {"Zh_tw": "1號出口"}}]
    mocker.patch("bot.mrt._tdx_get", new=AsyncMock(side_effect=[exits, None]))

    stations = await _load_system_stations("TRTC")

    assert stations["S1"]["exits"]
    assert "TRTC" not in mrt_module._station_cache  # 設施抓不到時不快取，避免誤快取成「真的沒有設施」


async def test_load_system_stations_uses_cache_within_ttl(mocker):
    tdx_get_mock = AsyncMock()
    mocker.patch("bot.mrt._tdx_get", new=tdx_get_mock)
    mrt_module._station_cache["TRTC"] = {
        "expires_at": mrt_module.time.time() + 100,
        "stations": {"cached": True},
    }

    stations = await _load_system_stations("TRTC")

    assert stations == {"cached": True}
    tdx_get_mock.assert_not_called()


# ---- _load_system_lines -------------------------------------------------------


async def test_load_system_lines_builds_sorted_station_list(mocker):
    lines_data = [{"LineID": "L1", "LineName": {"Zh_tw": "測試線"}}]
    stations_of_line = [
        {
            "LineID": "L1",
            "Stations": [
                {"Sequence": 2, "StationID": "S2", "StationName": {"Zh_tw": "第二站"}},
                {"Sequence": 1, "StationID": "S1", "StationName": {"Zh_tw": "第一站"}},
            ],
        }
    ]
    mocker.patch("bot.mrt._tdx_get", new=AsyncMock(side_effect=[lines_data, stations_of_line]))

    lines = await _load_system_lines("TRTC")

    assert lines["L1"]["name"] == "測試線"
    assert lines["L1"]["stations"] == [("S1", "第一站"), ("S2", "第二站")]


async def test_load_system_lines_returns_none_when_stations_of_line_missing(mocker):
    lines_data = [{"LineID": "L1", "LineName": {"Zh_tw": "測試線"}}]
    mocker.patch("bot.mrt._tdx_get", new=AsyncMock(side_effect=[lines_data, None]))

    assert await _load_system_lines("TRTC") is None
    assert "TRTC" not in mrt_module._line_cache


# ---- _format_station_text -----------------------------------------------------


def test_format_station_text_sorts_exits_and_shows_all_sections():
    station = {
        "name": "測試站",
        "exits": [
            {"ExitID": "2", "ExitName": {"Zh_tw": "2號出口"}, "Stair": True, "Elevator": False, "Escalator": 1},
            {"ExitID": "1", "ExitName": {"Zh_tw": "1號出口"}, "Stair": False, "Elevator": True, "Escalator": 0},
        ],
        "elevators": [{"FloorLevel": "B1", "Description": "近1號出口"}],
        "toilets": [],
        "drinking_fountains": [{"FloorLevel": "", "Description": "近2號出口"}],
        "facility_map_urls": [],
    }

    text = _format_station_text(station)

    assert text.index("1號出口") < text.index("2號出口")
    assert "樓梯：❌｜電梯：⭕｜手扶梯：❌" in text  # 1號出口
    assert "樓梯：⭕｜電梯：❌｜手扶梯：↕️" in text  # 2號出口
    assert "♿ 無障礙電梯位置" in text
    assert "B1 近1號出口" in text
    assert "🚻 廁所：查無資料" in text
    assert "🚰 飲水機位置" in text
    assert "近2號出口" in text


def test_format_station_text_shows_no_data_message_when_no_facilities():
    station = {
        "name": "測試站",
        "exits": [],
        "elevators": [],
        "toilets": [],
        "drinking_fountains": [],
        "facility_map_urls": [],
    }

    text = _format_station_text(station)

    assert "🚻 廁所：查無資料" in text
    assert "🚰 飲水機：查無資料" in text
    assert "♿ 無障礙電梯位置" not in text
    assert "車站資訊圖" not in text  # 沒有 facility_map_urls 就不該顯示這段


def test_format_station_text_shows_facility_map_when_toilets_and_drinking_missing():
    station = {
        "name": "測試站",
        "exits": [],
        "elevators": [],
        "toilets": [],
        "drinking_fountains": [],
        "facility_map_urls": [{"MapName": {"Zh_tw": "測試站資訊圖"}, "MapURL": "https://example.test/map.pdf"}],
    }

    text = _format_station_text(station)

    assert "🗺 查無詳細位置時，可以參考車站資訊圖" in text
    assert "測試站資訊圖：https://example.test/map.pdf" in text


def test_format_station_text_hides_facility_map_when_toilets_and_drinking_present():
    station = {
        "name": "測試站",
        "exits": [],
        "elevators": [],
        "toilets": [{"Description": "廁所A"}],
        "drinking_fountains": [{"Description": "飲水機A"}],
        "facility_map_urls": [{"MapName": {"Zh_tw": "測試站資訊圖"}, "MapURL": "https://example.test/map.pdf"}],
    }

    text = _format_station_text(station)

    assert "車站資訊圖" not in text


# ---- handlers -----------------------------------------------------------------


async def test_mrt_command_sends_rail_system_keyboard(make_update, make_context):
    update = make_update(text="/mrt")

    await mrt(update, make_context())

    update.message.reply_text.assert_awaited_once()
    _, kwargs = update.message.reply_text.call_args
    all_texts = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert "臺北捷運" in all_texts


@pytest.mark.parametrize(
    "callback_data, handler_name",
    [
        ("mrt:system:TRTC", "handle_mrt_system_callback"),
        ("mrt:line:TRTC:L1", "handle_mrt_line_callback"),
        ("mrt:station:TRTC:S1", "handle_mrt_station_callback"),
        ("fare:system:TRTC", "handle_fare_system_callback"),
        ("fare:origin_line:TRTC:L1", "handle_fare_origin_line_callback"),
        ("fare:origin_station:TRTC:S1", "handle_fare_origin_station_callback"),
        ("fare:dest_line:TRTC:S1:L2", "handle_fare_dest_line_callback"),
        ("fare:dest_station:TRTC:S1:S2", "handle_fare_dest_station_callback"),
        ("mrttime:system:TRTC", "handle_mrttime_system_callback"),
        ("mrttime:oline:TRTC:L1", "handle_mrttime_origin_line_callback"),
        ("mrttime:ostn:TRTC:S1", "handle_mrttime_origin_station_callback"),
        ("mrttime:dline:TRTC:S1:L2", "handle_mrttime_dest_line_callback"),
        ("mrttime:dstn:TRTC:S1:S2", "handle_mrttime_dest_station_callback"),
    ],
)
async def test_tdx_callbacks_dismiss_menu_buttons(
    make_callback_update, make_context, mocker, callback_data, handler_name
):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", "id")
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", "secret")
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=None))
    mocker.patch("bot.mrt._load_system_stations", new=AsyncMock(return_value=None))
    mocker.patch("bot.mrt._load_system_travel_times", new=AsyncMock(return_value=None))
    mocker.patch("bot.mrt._fetch_od_fare", new=AsyncMock(return_value=None))
    update = make_callback_update(callback_data)
    update.callback_query.edit_message_reply_markup = AsyncMock()

    await getattr(mrt_module, handler_name)(update, make_context())

    update.callback_query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)


async def test_handle_mrt_system_callback_without_credentials_notifies_admin(
    make_callback_update, make_context, mocker
):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", None)
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", None)
    update = make_callback_update("mrt:system:TRTC")
    context = make_context()

    await handle_mrt_system_callback(update, context)

    update.callback_query.answer.assert_awaited_once()
    text = context.bot.send_message.call_args.args[1]
    assert "TDX_CLIENT_ID" in text


async def test_handle_mrt_system_callback_no_lines_sends_error(make_callback_update, make_context, mocker):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", "id")
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", "secret")
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=None))
    update = make_callback_update("mrt:system:TRTC")
    context = make_context()

    await handle_mrt_system_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到" in text


async def test_handle_mrt_system_callback_success_sends_line_keyboard(make_callback_update, make_context, mocker):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", "id")
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", "secret")
    lines = {"L1": {"name": "測試線", "stations": [("S1", "第一站")]}}
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=lines))
    update = make_callback_update("mrt:system:TRTC")
    context = make_context()

    await handle_mrt_system_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    buttons = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["測試線"]


async def test_handle_mrt_line_callback_missing_line_sends_error(make_callback_update, make_context, mocker):
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value={}))
    update = make_callback_update("mrt:line:TRTC:L1")
    context = make_context()

    await handle_mrt_line_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到這條路線" in text


async def test_handle_mrt_line_callback_success_sends_station_keyboard(make_callback_update, make_context, mocker):
    lines = {"L1": {"name": "測試線", "stations": [("S1", "第一站"), ("S2", "第二站")]}}
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=lines))
    update = make_callback_update("mrt:line:TRTC:L1")
    context = make_context()

    await handle_mrt_line_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    buttons = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["第一站", "第二站"]


async def test_handle_mrt_station_callback_missing_station_sends_error(make_callback_update, make_context, mocker):
    mocker.patch("bot.mrt._load_system_stations", new=AsyncMock(return_value={}))
    update = make_callback_update("mrt:station:TRTC:S1")
    context = make_context()

    await handle_mrt_station_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到這一站" in text


async def test_handle_mrt_station_callback_success_sends_formatted_text(make_callback_update, make_context, mocker):
    station = {
        "name": "測試站",
        "exits": [],
        "elevators": [],
        "toilets": [],
        "drinking_fountains": [],
        "facility_map_urls": [],
    }
    mocker.patch("bot.mrt._load_system_stations", new=AsyncMock(return_value={"S1": station}))
    update = make_callback_update("mrt:station:TRTC:S1")
    context = make_context()

    await handle_mrt_station_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "測試站" in text


# ---- _fetch_od_fare ------------------------------------------------------------


async def test_fetch_od_fare_returns_first_result(mocker):
    fare_record = {"OriginStationID": "S1", "DestinationStationID": "S2"}
    tdx_get_mock = AsyncMock(return_value=[fare_record])
    mocker.patch("bot.mrt._tdx_get", new=tdx_get_mock)

    result = await _fetch_od_fare("TRTC", "S1", "S2")

    assert result == fare_record
    tdx_get_mock.assert_awaited_once_with(
        "/v2/Rail/Metro/ODFare/TRTC", **{"$filter": "OriginStationID eq 'S1' and DestinationStationID eq 'S2'"}
    )


async def test_fetch_od_fare_returns_none_when_empty(mocker):
    mocker.patch("bot.mrt._tdx_get", new=AsyncMock(return_value=[]))

    assert await _fetch_od_fare("TRTC", "S1", "S2") is None


async def test_fetch_od_fare_returns_none_when_request_fails(mocker):
    mocker.patch("bot.mrt._tdx_get", new=AsyncMock(return_value=None))

    assert await _fetch_od_fare("TRTC", "S1", "S2") is None


# ---- _format_fare_text ----------------------------------------------------------


def test_format_fare_text_shows_full_fare_and_distance():
    fare = {
        "OriginStationName": {"Zh_tw": "頂埔"},
        "DestinationStationName": {"Zh_tw": "淡水"},
        "Fares": [
            {"TicketType": 1, "FareClass": 1, "Price": 65},
            {"TicketType": 1, "FareClass": 3, "CitizenCode": "NWT", "Price": 26},
        ],
        "TravelDistance": 36.87,
    }

    text = _format_fare_text(fare)

    assert "頂埔 → 淡水" in text
    assert "全票票價：NT$ 65" in text
    assert "36.87" in text


def test_format_fare_text_skips_distance_when_zero():
    fare = {
        "OriginStationName": {"Zh_tw": "頂埔"},
        "DestinationStationName": {"Zh_tw": "頂埔"},
        "Fares": [{"TicketType": 1, "FareClass": 1, "Price": 20}],
        "TravelDistance": 0,
    }

    text = _format_fare_text(fare)

    assert "全票票價：NT$ 20" in text
    assert "里程" not in text


def test_format_fare_text_shows_placeholder_when_full_fare_missing():
    fare = {
        "OriginStationName": {"Zh_tw": "頂埔"},
        "DestinationStationName": {"Zh_tw": "淡水"},
        "Fares": [{"TicketType": 1, "FareClass": 3, "CitizenCode": "NWT", "Price": 26}],
        "TravelDistance": 10,
    }

    text = _format_fare_text(fare)

    assert "查無全票票價資料" in text


# ---- fare handlers --------------------------------------------------------------


async def test_mrtfare_command_sends_rail_system_keyboard(make_update, make_context):
    update = make_update(text="/mrtfare")

    await mrtfare(update, make_context())

    update.message.reply_text.assert_awaited_once()
    _, kwargs = update.message.reply_text.call_args
    all_texts = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert "臺北捷運" in all_texts


async def test_handle_fare_system_callback_without_credentials_notifies_admin(
    make_callback_update, make_context, mocker
):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", None)
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", None)
    update = make_callback_update("fare:system:TRTC")
    context = make_context()

    await handle_fare_system_callback(update, context)

    update.callback_query.answer.assert_awaited_once()
    text = context.bot.send_message.call_args.args[1]
    assert "TDX_CLIENT_ID" in text


async def test_handle_fare_system_callback_no_lines_sends_error(make_callback_update, make_context, mocker):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", "id")
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", "secret")
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=None))
    update = make_callback_update("fare:system:TRTC")
    context = make_context()

    await handle_fare_system_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到" in text


async def test_handle_fare_system_callback_success_sends_origin_line_keyboard(
    make_callback_update, make_context, mocker
):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", "id")
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", "secret")
    lines = {"L1": {"name": "測試線", "stations": [("S1", "第一站")]}}
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=lines))
    update = make_callback_update("fare:system:TRTC")
    context = make_context()

    await handle_fare_system_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    buttons = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    callback_data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["測試線"]
    assert callback_data == ["fare:origin_line:TRTC:L1"]


async def test_handle_fare_origin_line_callback_missing_line_sends_error(make_callback_update, make_context, mocker):
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value={}))
    update = make_callback_update("fare:origin_line:TRTC:L1")
    context = make_context()

    await handle_fare_origin_line_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到這條路線" in text


async def test_handle_fare_origin_line_callback_success_sends_origin_station_keyboard(
    make_callback_update, make_context, mocker
):
    lines = {"L1": {"name": "測試線", "stations": [("S1", "第一站"), ("S2", "第二站")]}}
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=lines))
    update = make_callback_update("fare:origin_line:TRTC:L1")
    context = make_context()

    await handle_fare_origin_line_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    callback_data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert callback_data == ["fare:origin_station:TRTC:S1", "fare:origin_station:TRTC:S2"]


async def test_handle_fare_origin_station_callback_no_lines_sends_error(make_callback_update, make_context, mocker):
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=None))
    update = make_callback_update("fare:origin_station:TRTC:S1")
    context = make_context()

    await handle_fare_origin_station_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到路線資料" in text


async def test_handle_fare_origin_station_callback_success_sends_dest_line_keyboard(
    make_callback_update, make_context, mocker
):
    lines = {"L1": {"name": "測試線", "stations": [("S1", "第一站")]}}
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=lines))
    update = make_callback_update("fare:origin_station:TRTC:S1")
    context = make_context()

    await handle_fare_origin_station_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    callback_data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert callback_data == ["fare:dest_line:TRTC:S1:L1"]


async def test_handle_fare_dest_line_callback_missing_line_sends_error(make_callback_update, make_context, mocker):
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value={}))
    update = make_callback_update("fare:dest_line:TRTC:S1:L2")
    context = make_context()

    await handle_fare_dest_line_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到這條路線" in text


async def test_handle_fare_dest_line_callback_success_sends_dest_station_keyboard(
    make_callback_update, make_context, mocker
):
    lines = {"L2": {"name": "測試線二", "stations": [("S2", "第二站"), ("S3", "第三站")]}}
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=lines))
    update = make_callback_update("fare:dest_line:TRTC:S1:L2")
    context = make_context()

    await handle_fare_dest_line_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    callback_data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert callback_data == ["fare:dest_station:TRTC:S1:S2", "fare:dest_station:TRTC:S1:S3"]


async def test_handle_fare_dest_station_callback_missing_fare_sends_error(make_callback_update, make_context, mocker):
    mocker.patch("bot.mrt._fetch_od_fare", new=AsyncMock(return_value=None))
    update = make_callback_update("fare:dest_station:TRTC:S1:S2")
    context = make_context()

    await handle_fare_dest_station_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到這兩站之間的票價" in text


async def test_handle_fare_dest_station_callback_success_sends_formatted_text(
    make_callback_update, make_context, mocker
):
    fare = {
        "OriginStationName": {"Zh_tw": "頂埔"},
        "DestinationStationName": {"Zh_tw": "淡水"},
        "Fares": [{"TicketType": 1, "FareClass": 1, "Price": 65}],
        "TravelDistance": 36.87,
    }
    mocker.patch("bot.mrt._fetch_od_fare", new=AsyncMock(return_value=fare))
    update = make_callback_update("fare:dest_station:TRTC:S1:S2")
    context = make_context()

    await handle_fare_dest_station_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "頂埔 → 淡水" in text
    assert "NT$ 65" in text


# ---- _load_system_travel_times ------------------------------------------------


async def test_load_system_travel_times_flattens_segments(mocker):
    data = [
        {
            "LineID": "L1",
            "TravelTimes": [
                {"FromStationID": "S1", "ToStationID": "S2", "RunTime": 60, "StopTime": 20},
                {"FromStationID": "S2", "ToStationID": "S3", "RunTime": 90, "StopTime": 25},
            ],
        }
    ]
    mocker.patch("bot.mrt._tdx_get", new=AsyncMock(return_value=data))

    segments = await _load_system_travel_times("TRTC")

    assert segments[("S1", "S2")] == {"run": 60, "stop": 20}
    assert segments[("S2", "S3")] == {"run": 90, "stop": 25}


async def test_load_system_travel_times_returns_none_when_request_fails(mocker):
    mocker.patch("bot.mrt._tdx_get", new=AsyncMock(return_value=None))

    assert await _load_system_travel_times("TRTC") is None


async def test_load_system_travel_times_uses_cache_within_ttl(mocker):
    tdx_get_mock = AsyncMock()
    mocker.patch("bot.mrt._tdx_get", new=tdx_get_mock)
    mrt_module._travel_time_cache["TRTC"] = {
        "expires_at": mrt_module.time.time() + 100,
        "segments": {("S1", "S2"): {"run": 1, "stop": 2}},
    }

    segments = await _load_system_travel_times("TRTC")

    assert segments == {("S1", "S2"): {"run": 1, "stop": 2}}
    tdx_get_mock.assert_not_called()


# ---- _interchange_groups --------------------------------------------------


def test_interchange_groups_matches_same_name_across_lines():
    lines = {
        "BL": {"name": "板南線", "stations": [("BL15", "忠孝復興"), ("BL14", "忠孝新生")]},
        "BR": {"name": "文湖線", "stations": [("BR10", "忠孝復興"), ("BR09", "大安")]},
        "R": {"name": "淡水信義線", "stations": [("R05", "大安"), ("R08", "中正紀念堂")]},
    }

    groups = sorted(_interchange_groups(lines))

    assert groups == [["BL15", "BR10"], ["BR09", "R05"]]  # 忠孝復興、大安；忠孝新生單線不算


def test_interchange_groups_empty_when_no_shared_names():
    lines = {"L1": {"name": "一號線", "stations": [("A1", "甲"), ("A2", "乙")]}}

    assert _interchange_groups(lines) == []


# ---- _build_travel_graph / _shortest_travel --------------------------------

SEGMENTS = {
    ("BL1", "BL2"): {"run": 100, "stop": 20},
    ("BL2", "BL3"): {"run": 110, "stop": 20},
    ("R1", "R2"): {"run": 90, "stop": 20},
    ("R2", "R3"): {"run": 95, "stop": 25},
}
GROUPS = [["BL2", "R2"]]  # 忠孝復興：兩條線各一個月台


def test_build_travel_graph_adds_bidirectional_ride_and_transfer_edges():
    graph = _build_travel_graph(SEGMENTS, GROUPS)

    assert ("BL2", 120, "ride") in graph["BL1"]
    assert ("BL1", 120, "ride") in graph["BL2"]  # 搭車段雙向
    assert ("R2", mrt_module.INTERCHANGE_WALK_SECONDS, "transfer") in graph["BL2"]
    assert ("BL2", mrt_module.INTERCHANGE_WALK_SECONDS, "transfer") in graph["R2"]


def test_shortest_travel_same_line_has_no_transfer():
    graph = _build_travel_graph(SEGMENTS, GROUPS)

    total, ride, transfer, nodes = _shortest_travel(graph, "BL1", "BL3")

    assert (total, ride, transfer, nodes) == (250, 250, 0, [])


def test_shortest_travel_cross_line_splits_ride_and_transfer():
    graph = _build_travel_graph(SEGMENTS, GROUPS)
    walk = mrt_module.INTERCHANGE_WALK_SECONDS

    total, ride, transfer, nodes = _shortest_travel(graph, "BL1", "R3")

    assert total == 120 + walk + 120
    assert ride == 240
    assert transfer == walk
    assert nodes == ["BL2"]


def test_shortest_travel_returns_zero_for_same_station():
    graph = _build_travel_graph(SEGMENTS, GROUPS)

    assert _shortest_travel(graph, "BL1", "BL1") == (0, 0, 0, [])


def test_shortest_travel_returns_none_when_no_path():
    graph = _build_travel_graph(SEGMENTS, [])  # 沒有轉乘站，BL 線到不了 R 線

    assert _shortest_travel(graph, "BL1", "R3") is None


def test_shortest_travel_returns_none_when_station_unknown():
    graph = _build_travel_graph(SEGMENTS, GROUPS)

    assert _shortest_travel(graph, "BL1", "X9") is None


# ---- _format_travel_time_text --------------------------------------------------


def test_format_travel_time_text_shows_transfer_breakdown():
    text = _format_travel_time_text(
        "臺北捷運", "永寧", "淡水", {"BL2": "忠孝復興"}, (420, 240, 180, ["BL2"])
    )

    assert "🚇 永寧 → 淡水" in text
    assert "最少約 7 分鐘" in text
    assert "車上約 4 分 + 轉乘步行約 3 分" in text
    assert "🔁 轉乘 1 次：忠孝復興" in text


def test_format_travel_time_text_without_transfer_omits_breakdown():
    text = _format_travel_time_text("臺北捷運", "永寧", "南港", {}, (250, 250, 0, []))

    assert "最少約 4 分鐘" in text
    assert "轉乘" not in text
    assert "車上約" not in text


# ---- mrttime handlers --------------------------------------------------------


async def test_mrttime_command_sends_rail_system_keyboard(make_update, make_context):
    update = make_update(text="/mrttime")

    await mrttime(update, make_context())

    _, kwargs = update.message.reply_text.call_args
    all_texts = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert "臺北捷運" in all_texts


async def test_handle_mrttime_system_callback_without_credentials_notifies_admin(
    make_callback_update, make_context, mocker
):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", None)
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", None)
    update = make_callback_update("mrttime:system:TRTC")
    context = make_context()

    await handle_mrttime_system_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "TDX_CLIENT_ID" in text


async def test_handle_mrttime_system_callback_success_sends_origin_line_keyboard(
    make_callback_update, make_context, mocker
):
    mocker.patch("bot.mrt.TDX_CLIENT_ID", "id")
    mocker.patch("bot.mrt.TDX_CLIENT_SECRET", "secret")
    lines = {"L1": {"name": "測試線", "stations": [("S1", "第一站")]}}
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=lines))
    update = make_callback_update("mrttime:system:TRTC")
    context = make_context()

    await handle_mrttime_system_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    callback_data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert callback_data == ["mrttime:oline:TRTC:L1"]


async def test_handle_mrttime_origin_line_callback_sends_origin_station_keyboard(
    make_callback_update, make_context, mocker
):
    lines = {"L1": {"name": "測試線", "stations": [("S1", "第一站"), ("S2", "第二站")]}}
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=lines))
    update = make_callback_update("mrttime:oline:TRTC:L1")
    context = make_context()

    await handle_mrttime_origin_line_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    callback_data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert callback_data == ["mrttime:ostn:TRTC:S1", "mrttime:ostn:TRTC:S2"]


async def test_handle_mrttime_origin_station_callback_sends_dest_line_keyboard(
    make_callback_update, make_context, mocker
):
    lines = {"L1": {"name": "測試線", "stations": [("S1", "第一站")]}}
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=lines))
    update = make_callback_update("mrttime:ostn:TRTC:S1")
    context = make_context()

    await handle_mrttime_origin_station_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    callback_data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert callback_data == ["mrttime:dline:TRTC:S1:L1"]


async def test_handle_mrttime_dest_line_callback_excludes_origin_station(
    make_callback_update, make_context, mocker
):
    lines = {"L2": {"name": "測試線二", "stations": [("S1", "第一站"), ("S2", "第二站"), ("S3", "第三站")]}}
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=lines))
    update = make_callback_update("mrttime:dline:TRTC:S1:L2")
    context = make_context()

    await handle_mrttime_dest_line_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    callback_data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert callback_data == ["mrttime:dstn:TRTC:S1:S2", "mrttime:dstn:TRTC:S1:S3"]


_CROSS_LINE_LINES = {
    "BL": {"name": "板南線", "stations": [("BL1", "永寧"), ("BL2", "忠孝復興"), ("BL3", "南港")]},
    "R": {"name": "淡水信義線", "stations": [("R1", "象山"), ("R2", "忠孝復興"), ("R3", "淡水")]},
}
_DISCONNECTED_LINES = {
    "BL": {"name": "板南線", "stations": [("BL1", "永寧"), ("BL2", "板橋"), ("BL3", "南港")]},
    "R": {"name": "淡水信義線", "stations": [("R1", "象山"), ("R2", "大安"), ("R3", "淡水")]},
}


async def test_handle_mrttime_dest_station_callback_no_path_sends_error(
    make_callback_update, make_context, mocker
):
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=_DISCONNECTED_LINES))
    mocker.patch("bot.mrt._load_system_travel_times", new=AsyncMock(return_value=SEGMENTS))
    update = make_callback_update("mrttime:dstn:TRTC:BL1:R3")
    context = make_context()

    await handle_mrttime_dest_station_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到這兩站之間的行車時間" in text


async def test_handle_mrttime_dest_station_callback_missing_travel_times_sends_error(
    make_callback_update, make_context, mocker
):
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=_CROSS_LINE_LINES))
    mocker.patch("bot.mrt._load_system_travel_times", new=AsyncMock(return_value=None))
    update = make_callback_update("mrttime:dstn:TRTC:BL1:R3")
    context = make_context()

    await handle_mrttime_dest_station_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到這兩站之間的行車時間" in text


async def test_handle_mrttime_dest_station_callback_cross_line_success(
    make_callback_update, make_context, mocker
):
    mocker.patch("bot.mrt._load_system_lines", new=AsyncMock(return_value=_CROSS_LINE_LINES))
    mocker.patch("bot.mrt._load_system_travel_times", new=AsyncMock(return_value=SEGMENTS))
    update = make_callback_update("mrttime:dstn:TRTC:BL1:R3")
    context = make_context()

    await handle_mrttime_dest_station_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "永寧 → 淡水" in text
    assert "🔁 轉乘 1 次：忠孝復興" in text
