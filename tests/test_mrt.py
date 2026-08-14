from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import bot.mrt as mrt_module
from bot.mrt import (
    _format_station_text,
    _get_access_token,
    _load_system_lines,
    _load_system_stations,
    _tdx_get,
    chunk,
    handle_mrt_line_callback,
    handle_mrt_station_callback,
    handle_mrt_system_callback,
    mrt,
)


@pytest.fixture(autouse=True)
def reset_mrt_module_caches():
    """mrt.py 用 module-level dict 做 cache，測試之間要清乾淨避免互相汙染。"""
    mrt_module._token_cache["access_token"] = None
    mrt_module._token_cache["expires_at"] = 0.0
    mrt_module._station_cache.clear()
    mrt_module._line_cache.clear()
    yield
    mrt_module._token_cache["access_token"] = None
    mrt_module._token_cache["expires_at"] = 0.0
    mrt_module._station_cache.clear()
    mrt_module._line_cache.clear()


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
        }
    ]
    mocker.patch("bot.mrt._tdx_get", new=AsyncMock(side_effect=[exits, facilities]))

    stations = await _load_system_stations("TRTC")

    assert stations["S1"]["name"] == "測試站"
    assert len(stations["S1"]["exits"]) == 1
    assert stations["S1"]["elevators"] == [{"Description": "電梯A"}]
    assert stations["S1"]["toilets"] == [{"Description": "廁所A"}]
    assert stations["S1"]["drinking_fountains"] == [{"Description": "飲水機A"}]


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
    station = {"name": "測試站", "exits": [], "elevators": [], "toilets": [], "drinking_fountains": []}

    text = _format_station_text(station)

    assert "🚻 廁所：查無資料" in text
    assert "🚰 飲水機：查無資料" in text
    assert "♿ 無障礙電梯位置" not in text


# ---- handlers -----------------------------------------------------------------


async def test_mrt_command_sends_rail_system_keyboard(make_update, make_context):
    update = make_update(text="/mrt")

    await mrt(update, make_context())

    update.message.reply_text.assert_awaited_once()
    _, kwargs = update.message.reply_text.call_args
    all_texts = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert "臺北捷運" in all_texts


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
    station = {"name": "測試站", "exits": [], "elevators": [], "toilets": [], "drinking_fountains": []}
    mocker.patch("bot.mrt._load_system_stations", new=AsyncMock(return_value={"S1": station}))
    update = make_callback_update("mrt:station:TRTC:S1")
    context = make_context()

    await handle_mrt_station_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "測試站" in text
