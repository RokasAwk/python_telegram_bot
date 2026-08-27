from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import bot.thsr as thsr_module
from bot.thsr import (
    _duration_minutes,
    _fetch_daily_timetable,
    _fetch_od_fare,
    _format_duration,
    _format_fare_text,
    _format_timetable_text,
    _get_access_token,
    _load_stations,
    _tdx_get,
    chunk,
    handle_thsrfare_dest_callback,
    handle_thsrfare_origin_callback,
    handle_thsrtime_dest_callback,
    handle_thsrtime_origin_callback,
    thsrfare,
    thsrtime,
)


@pytest.fixture(autouse=True)
def reset_thsr_module_caches():
    """thsr.py 用 module-level dict 做 cache，測試之間要清乾淨避免互相汙染。"""
    thsr_module._token_cache["access_token"] = None
    thsr_module._token_cache["expires_at"] = 0.0
    thsr_module._station_cache["stations"] = {}
    thsr_module._station_cache["expires_at"] = 0.0
    yield
    thsr_module._token_cache["access_token"] = None
    thsr_module._token_cache["expires_at"] = 0.0
    thsr_module._station_cache["stations"] = {}
    thsr_module._station_cache["expires_at"] = 0.0


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
    mocker.patch("bot.thsr.httpx.AsyncClient", client_cls)
    return client


def test_chunk_splits_into_fixed_size_groups():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunk_with_empty_list():
    assert chunk([], 3) == []


# ---- _get_access_token ----------------------------------------------------


async def test_get_access_token_returns_none_without_credentials(mocker):
    mocker.patch("bot.thsr.TDX_CLIENT_ID", None)
    mocker.patch("bot.thsr.TDX_CLIENT_SECRET", None)

    assert await _get_access_token() is None


async def test_get_access_token_fetches_and_caches_new_token(mocker, mock_async_client):
    mocker.patch("bot.thsr.TDX_CLIENT_ID", "id")
    mocker.patch("bot.thsr.TDX_CLIENT_SECRET", "secret")
    mock_async_client.post.return_value = FakeResponse({"access_token": "tok123", "expires_in": 3600})

    token = await _get_access_token()

    assert token == "tok123"
    assert thsr_module._token_cache["access_token"] == "tok123"
    mock_async_client.post.assert_awaited_once()


async def test_get_access_token_reuses_cached_token_without_new_request(mocker, mock_async_client):
    mocker.patch("bot.thsr.TDX_CLIENT_ID", "id")
    mocker.patch("bot.thsr.TDX_CLIENT_SECRET", "secret")
    thsr_module._token_cache["access_token"] = "cached-tok"
    thsr_module._token_cache["expires_at"] = thsr_module.time.time() + 100

    token = await _get_access_token()

    assert token == "cached-tok"
    mock_async_client.post.assert_not_called()


async def test_get_access_token_returns_none_on_http_error(mocker, mock_async_client):
    mocker.patch("bot.thsr.TDX_CLIENT_ID", "id")
    mocker.patch("bot.thsr.TDX_CLIENT_SECRET", "secret")
    mock_async_client.post.return_value = FakeResponse({}, raise_error=True)

    assert await _get_access_token() is None


# ---- _tdx_get ---------------------------------------------------------------


async def test_tdx_get_returns_none_when_no_token(mocker):
    mocker.patch("bot.thsr._get_access_token", new=AsyncMock(return_value=None))

    assert await _tdx_get("/some/path") is None


async def test_tdx_get_returns_json_on_success(mocker, mock_async_client):
    mocker.patch("bot.thsr._get_access_token", new=AsyncMock(return_value="tok"))
    mock_async_client.get.return_value = FakeResponse([{"a": 1}])

    result = await _tdx_get("/some/path")

    assert result == [{"a": 1}]


async def test_tdx_get_returns_none_on_http_error(mocker, mock_async_client):
    mocker.patch("bot.thsr._get_access_token", new=AsyncMock(return_value="tok"))
    mock_async_client.get.return_value = FakeResponse({}, raise_error=True)

    assert await _tdx_get("/some/path") is None


# ---- _load_stations ---------------------------------------------------------


async def test_load_stations_builds_id_to_name_map(mocker):
    stations_data = [
        {"StationID": "1000", "StationName": {"Zh_tw": "台北"}},
        {"StationID": "1070", "StationName": {"Zh_tw": "左營"}},
    ]
    mocker.patch("bot.thsr._tdx_get", new=AsyncMock(return_value=stations_data))

    stations = await _load_stations()

    assert stations == {"1000": "台北", "1070": "左營"}


async def test_load_stations_returns_none_when_request_fails(mocker):
    mocker.patch("bot.thsr._tdx_get", new=AsyncMock(return_value=None))

    assert await _load_stations() is None


async def test_load_stations_uses_cache_within_ttl(mocker):
    tdx_get_mock = AsyncMock()
    mocker.patch("bot.thsr._tdx_get", new=tdx_get_mock)
    thsr_module._station_cache["stations"] = {"1000": "台北"}
    thsr_module._station_cache["expires_at"] = thsr_module.time.time() + 100

    stations = await _load_stations()

    assert stations == {"1000": "台北"}
    tdx_get_mock.assert_not_called()


# ---- _fetch_daily_timetable ---------------------------------------------------


async def test_fetch_daily_timetable_calls_correct_path(mocker):
    tdx_get_mock = AsyncMock(return_value=[{"a": 1}])
    mocker.patch("bot.thsr._tdx_get", new=tdx_get_mock)

    result = await _fetch_daily_timetable("1000", "1070", "2026-08-19")

    assert result == [{"a": 1}]
    tdx_get_mock.assert_awaited_once_with("/v2/Rail/THSR/DailyTimetable/OD/1000/to/1070/2026-08-19")


async def test_fetch_daily_timetable_returns_none_when_request_fails(mocker):
    mocker.patch("bot.thsr._tdx_get", new=AsyncMock(return_value=None))

    assert await _fetch_daily_timetable("1000", "1070", "2026-08-19") is None


# ---- _fetch_od_fare -------------------------------------------------------------


async def test_fetch_od_fare_returns_first_result(mocker):
    fare_record = {"OriginStationID": "1000", "DestinationStationID": "1070"}
    tdx_get_mock = AsyncMock(return_value=[fare_record])
    mocker.patch("bot.thsr._tdx_get", new=tdx_get_mock)

    result = await _fetch_od_fare("1000", "1070")

    assert result == fare_record
    tdx_get_mock.assert_awaited_once_with("/v2/Rail/THSR/ODFare/1000/to/1070")


async def test_fetch_od_fare_returns_none_when_empty(mocker):
    mocker.patch("bot.thsr._tdx_get", new=AsyncMock(return_value=[]))

    assert await _fetch_od_fare("1000", "1070") is None


async def test_fetch_od_fare_returns_none_when_request_fails(mocker):
    mocker.patch("bot.thsr._tdx_get", new=AsyncMock(return_value=None))

    assert await _fetch_od_fare("1000", "1070") is None


# ---- _duration_minutes / _format_duration -------------------------------------------


def test_duration_minutes_computes_difference():
    assert _duration_minutes("06:26", "08:40") == 134


def test_format_duration_shows_hours_and_minutes():
    assert _format_duration(134) == "2小時14分"


def test_format_duration_shows_minutes_only_when_under_an_hour():
    assert _format_duration(25) == "25分"


# ---- _format_timetable_text ------------------------------------------------------


def test_format_timetable_text_sorts_by_departure_time():
    trains = [
        {
            "DailyTrainInfo": {"TrainNo": "0203"},
            "OriginStopTime": {"DepartureTime": "07:00"},
            "DestinationStopTime": {"ArrivalTime": "09:00"},
        },
        {
            "DailyTrainInfo": {"TrainNo": "0803"},
            "OriginStopTime": {"DepartureTime": "06:26"},
            "DestinationStopTime": {"ArrivalTime": "08:40"},
        },
    ]

    text = _format_timetable_text("台北", "左營", "2026-08-19", trains)

    assert text.index("0803") < text.index("0203")
    assert "🚆 班次 0803" in text
    assert "06:26 → 08:40｜2小時14分" in text
    assert "台北 → 左營（2026-08-19）" in text


def test_format_timetable_text_marks_fastest_train_with_badge():
    trains = [
        {
            "DailyTrainInfo": {"TrainNo": "0203"},
            "OriginStopTime": {"DepartureTime": "07:00"},
            "DestinationStopTime": {"ArrivalTime": "09:00"},  # 120 分
        },
        {
            "DailyTrainInfo": {"TrainNo": "0803"},
            "OriginStopTime": {"DepartureTime": "06:26"},
            "DestinationStopTime": {"ArrivalTime": "08:00"},  # 94 分，最快
        },
    ]

    text = _format_timetable_text("台北", "左營", "2026-08-19", trains)

    assert "🚆 班次 0803 ⚡" in text
    assert "🚆 班次 0203 ⚡" not in text
    assert "🚆 班次 0203" in text


def test_format_timetable_text_shows_no_data_message_when_empty():
    text = _format_timetable_text("台北", "左營", "2026-08-19", [])

    assert "查無班次資料" in text


# ---- _format_fare_text ------------------------------------------------------------


def test_format_fare_text_shows_standard_and_business_fare():
    fare = {
        "OriginStationName": {"Zh_tw": "台北"},
        "DestinationStationName": {"Zh_tw": "左營"},
        "Fares": [
            {"TicketType": 1, "FareClass": 1, "CabinClass": 1, "Price": 1490},
            {"TicketType": 1, "FareClass": 1, "CabinClass": 2, "Price": 2440},
            {"TicketType": 1, "FareClass": 9, "CabinClass": 1, "Price": 745},
        ],
    }

    text = _format_fare_text(fare)

    assert "台北 → 左營" in text
    assert "標準車廂全票：NT$ 1490" in text
    assert "商務車廂全票：NT$ 2440" in text


def test_format_fare_text_shows_placeholder_when_standard_fare_missing():
    fare = {
        "OriginStationName": {"Zh_tw": "台北"},
        "DestinationStationName": {"Zh_tw": "左營"},
        "Fares": [{"TicketType": 1, "FareClass": 9, "CabinClass": 1, "Price": 745}],
    }

    text = _format_fare_text(fare)

    assert "查無標準車廂全票票價資料" in text
    assert "商務車廂" not in text


# ---- callback menu buttons ------------------------------------------------------


@pytest.mark.parametrize(
    "callback_data, handler_name",
    [
        ("thsrtime:origin:0990", "handle_thsrtime_origin_callback"),
        ("thsrtime:dest:0990:1000", "handle_thsrtime_dest_callback"),
        ("thsrfare:origin:0990", "handle_thsrfare_origin_callback"),
        ("thsrfare:dest:0990:1000", "handle_thsrfare_dest_callback"),
    ],
)
async def test_tdx_callbacks_dismiss_menu_buttons(
    make_callback_update, make_context, mocker, callback_data, handler_name
):
    mocker.patch("bot.thsr._load_stations", new=AsyncMock(return_value=None))
    mocker.patch("bot.thsr._fetch_daily_timetable", new=AsyncMock(return_value=None))
    mocker.patch("bot.thsr._fetch_od_fare", new=AsyncMock(return_value=None))
    update = make_callback_update(callback_data)
    update.callback_query.edit_message_reply_markup = AsyncMock()

    await getattr(thsr_module, handler_name)(update, make_context())

    update.callback_query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)


# ---- thsrtime handlers -------------------------------------------------------------


async def test_thsrtime_command_without_credentials_notifies_admin(make_update, make_context, mocker):
    mocker.patch("bot.thsr.TDX_CLIENT_ID", None)
    mocker.patch("bot.thsr.TDX_CLIENT_SECRET", None)
    update = make_update(text="/thsrtime")

    await thsrtime(update, make_context())

    text = update.message.reply_text.call_args.args[0]
    assert "TDX_CLIENT_ID" in text


async def test_thsrtime_command_sends_station_keyboard(make_update, make_context, mocker):
    mocker.patch("bot.thsr.TDX_CLIENT_ID", "id")
    mocker.patch("bot.thsr.TDX_CLIENT_SECRET", "secret")
    mocker.patch("bot.thsr._load_stations", new=AsyncMock(return_value={"1000": "台北", "1070": "左營"}))
    update = make_update(text="/thsrtime")

    await thsrtime(update, make_context())

    _, kwargs = update.message.reply_text.call_args
    all_texts = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert "台北" in all_texts
    assert "左營" in all_texts


async def test_handle_thsrtime_origin_callback_no_stations_sends_error(make_callback_update, make_context, mocker):
    mocker.patch("bot.thsr._load_stations", new=AsyncMock(return_value=None))
    update = make_callback_update("thsrtime:origin:1000")
    context = make_context()

    await handle_thsrtime_origin_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到高鐵車站資料" in text


async def test_handle_thsrtime_origin_callback_excludes_origin_from_destination_keyboard(
    make_callback_update, make_context, mocker
):
    mocker.patch(
        "bot.thsr._load_stations",
        new=AsyncMock(return_value={"1000": "台北", "1070": "左營"}),
    )
    update = make_callback_update("thsrtime:origin:1000")
    context = make_context()

    await handle_thsrtime_origin_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    buttons = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    callback_data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["左營"]
    assert callback_data == ["thsrtime:dest:1000:1070"]


async def test_handle_thsrtime_dest_callback_fetch_fails_sends_error(make_callback_update, make_context, mocker):
    mocker.patch(
        "bot.thsr._load_stations",
        new=AsyncMock(return_value={"1000": "台北", "1070": "左營"}),
    )
    mocker.patch("bot.thsr._fetch_daily_timetable", new=AsyncMock(return_value=None))
    update = make_callback_update("thsrtime:dest:1000:1070")
    context = make_context()

    await handle_thsrtime_dest_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到這兩站之間的時刻表" in text


async def test_handle_thsrtime_dest_callback_success_sends_formatted_text(make_callback_update, make_context, mocker):
    mocker.patch(
        "bot.thsr._load_stations",
        new=AsyncMock(return_value={"1000": "台北", "1070": "左營"}),
    )
    trains = [
        {
            "DailyTrainInfo": {"TrainNo": "0803"},
            "OriginStopTime": {"DepartureTime": "06:26"},
            "DestinationStopTime": {"ArrivalTime": "08:40"},
        }
    ]
    mocker.patch("bot.thsr._fetch_daily_timetable", new=AsyncMock(return_value=trains))
    update = make_callback_update("thsrtime:dest:1000:1070")
    context = make_context()

    await handle_thsrtime_dest_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "台北 → 左營" in text
    assert "0803" in text


# ---- thsrfare handlers -------------------------------------------------------------


async def test_thsrfare_command_without_credentials_notifies_admin(make_update, make_context, mocker):
    mocker.patch("bot.thsr.TDX_CLIENT_ID", None)
    mocker.patch("bot.thsr.TDX_CLIENT_SECRET", None)
    update = make_update(text="/thsrfare")

    await thsrfare(update, make_context())

    text = update.message.reply_text.call_args.args[0]
    assert "TDX_CLIENT_ID" in text


async def test_thsrfare_command_sends_station_keyboard(make_update, make_context, mocker):
    mocker.patch("bot.thsr.TDX_CLIENT_ID", "id")
    mocker.patch("bot.thsr.TDX_CLIENT_SECRET", "secret")
    mocker.patch("bot.thsr._load_stations", new=AsyncMock(return_value={"1000": "台北", "1070": "左營"}))
    update = make_update(text="/thsrfare")

    await thsrfare(update, make_context())

    _, kwargs = update.message.reply_text.call_args
    all_texts = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert "台北" in all_texts


async def test_handle_thsrfare_origin_callback_excludes_origin_from_destination_keyboard(
    make_callback_update, make_context, mocker
):
    mocker.patch(
        "bot.thsr._load_stations",
        new=AsyncMock(return_value={"1000": "台北", "1070": "左營"}),
    )
    update = make_callback_update("thsrfare:origin:1000")
    context = make_context()

    await handle_thsrfare_origin_callback(update, context)

    kwargs = context.bot.send_message.call_args.kwargs
    callback_data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert callback_data == ["thsrfare:dest:1000:1070"]


async def test_handle_thsrfare_dest_callback_missing_fare_sends_error(make_callback_update, make_context, mocker):
    mocker.patch("bot.thsr._fetch_od_fare", new=AsyncMock(return_value=None))
    update = make_callback_update("thsrfare:dest:1000:1070")
    context = make_context()

    await handle_thsrfare_dest_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "查不到這兩站之間的票價" in text


async def test_handle_thsrfare_dest_callback_success_sends_formatted_text(make_callback_update, make_context, mocker):
    fare = {
        "OriginStationName": {"Zh_tw": "台北"},
        "DestinationStationName": {"Zh_tw": "左營"},
        "Fares": [{"TicketType": 1, "FareClass": 1, "CabinClass": 1, "Price": 1490}],
    }
    mocker.patch("bot.thsr._fetch_od_fare", new=AsyncMock(return_value=fare))
    update = make_callback_update("thsrfare:dest:1000:1070")
    context = make_context()

    await handle_thsrfare_dest_callback(update, context)

    text = context.bot.send_message.call_args.args[1]
    assert "台北 → 左營" in text
    assert "NT$ 1490" in text
