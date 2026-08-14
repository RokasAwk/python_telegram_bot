from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from bot.weather import (
    WEEKDAY_NAMES,
    _half_day_bucket,
    chunk,
    fetch_3day_weather_text,
    fetch_daily_weather_text,
    fetch_weekly_weather_text,
    handle_weather_city_callback,
    handle_weather_period_callback,
    weather,
)


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
    mocker.patch("bot.weather.httpx.AsyncClient", client_cls)
    return client


def test_chunk_splits_into_fixed_size_groups():
    assert chunk([1, 2, 3, 4], 3) == [[1, 2, 3], [4]]


@pytest.mark.parametrize(
    "hour, expected_half",
    [
        (18, "晚上"),
        (23, "晚上"),
        (6, "白天"),
        (17, "白天"),
    ],
)
def test_half_day_bucket_same_day_cases(hour, expected_half):
    start = datetime(2026, 8, 14, hour, 0)
    assert _half_day_bucket(start) == (date(2026, 8, 14), expected_half)


@pytest.mark.parametrize("hour", [0, 3, 5])
def test_half_day_bucket_before_6am_belongs_to_previous_nights_evening(hour):
    start = datetime(2026, 8, 15, hour, 0)
    assert _half_day_bucket(start) == (date(2026, 8, 14), "晚上")


# ---- weather() command ---------------------------------------------------


async def test_weather_command_sends_city_keyboard_with_user_mention(make_update, make_context):
    update = make_update(text="/weather")

    await weather(update, make_context())

    update.message.reply_text.assert_awaited_once()
    (text,), kwargs = update.message.reply_text.call_args
    assert "tg://user?id=111" in text
    assert kwargs["parse_mode"] == "Markdown"
    all_cities = [b.text for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert "臺北市" in all_cities


async def test_handle_weather_city_callback_sends_period_keyboard(make_callback_update, make_context):
    update = make_callback_update("weather:city:臺北市")
    context = make_context()

    await handle_weather_city_callback(update, context)

    update.callback_query.answer.assert_awaited_once()
    kwargs = context.bot.send_message.call_args.kwargs
    labels = [b.text for b in kwargs["reply_markup"].inline_keyboard[0]]
    assert labels == ["☀️ 當日天氣", "🌤 三天天氣", "🗓 一週天氣"]


@pytest.mark.parametrize(
    "period, target",
    [
        ("today", "bot.weather.fetch_daily_weather_text"),
        ("3day", "bot.weather.fetch_3day_weather_text"),
        ("week", "bot.weather.fetch_weekly_weather_text"),
    ],
)
async def test_handle_weather_period_callback_dispatches_to_matching_fetcher(
    make_callback_update, make_context, mocker, period, target
):
    fetch_mock = mocker.patch(target, new=AsyncMock(return_value="結果文字"))
    update = make_callback_update(f"weather:period:{period}:臺北市")
    context = make_context()

    await handle_weather_period_callback(update, context)

    fetch_mock.assert_awaited_once_with("臺北市")
    assert context.bot.send_message.call_args.args[1] == "結果文字"


# ---- fetch_daily_weather_text ---------------------------------------------


async def test_fetch_daily_weather_text_unknown_city_returns_error():
    text = await fetch_daily_weather_text("不存在市")
    assert "找不到" in text


async def test_fetch_daily_weather_text_missing_api_key_returns_setup_message(mocker):
    mocker.patch("bot.weather.CWA_API_KEY", None)
    text = await fetch_daily_weather_text("臺北市")
    assert "CWA_API_KEY" in text


async def test_fetch_daily_weather_text_http_error_returns_friendly_message(mocker, mock_async_client):
    mocker.patch("bot.weather.CWA_API_KEY", "key")
    mock_async_client.get.return_value = FakeResponse({}, raise_error=True)

    text = await fetch_daily_weather_text("臺北市")
    assert "晚點再試試看" in text


async def test_fetch_daily_weather_text_empty_locations_returns_not_found(mocker, mock_async_client):
    mocker.patch("bot.weather.CWA_API_KEY", "key")
    mock_async_client.get.return_value = FakeResponse({"records": {"location": []}})

    text = await fetch_daily_weather_text("臺北市")
    assert "找不到" in text


async def test_fetch_daily_weather_text_formats_first_two_periods(mocker, mock_async_client):
    mocker.patch("bot.weather.CWA_API_KEY", "key")
    data = {
        "records": {
            "location": [
                {
                    "weatherElement": [
                        {
                            "elementName": "Wx",
                            "time": [
                                {
                                    "startTime": "2026-08-14 18:00:00",
                                    "endTime": "2026-08-15 06:00:00",
                                    "parameter": {"parameterName": "多雲"},
                                },
                                {
                                    "startTime": "2026-08-15 06:00:00",
                                    "endTime": "2026-08-15 18:00:00",
                                    "parameter": {"parameterName": "晴時多雲"},
                                },
                            ],
                        },
                        {
                            "elementName": "MaxT",
                            "time": [{"parameter": {"parameterName": "30"}}, {"parameter": {"parameterName": "31"}}],
                        },
                        {
                            "elementName": "MinT",
                            "time": [{"parameter": {"parameterName": "25"}}, {"parameter": {"parameterName": "26"}}],
                        },
                        {
                            "elementName": "PoP",
                            "time": [{"parameter": {"parameterName": "10"}}, {"parameter": {"parameterName": "20"}}],
                        },
                    ]
                }
            ]
        }
    }
    mock_async_client.get.return_value = FakeResponse(data)

    text = await fetch_daily_weather_text("臺北市")

    assert "臺北市天氣預報" in text
    assert "08/14 18:00 - 08/15 06:00" in text
    assert "多雲" in text
    assert "25°C - 30°C" in text
    assert "降雨機率 10%" in text
    assert "晴時多雲" in text


# ---- fetch_3day_weather_text -----------------------------------------------


async def test_fetch_3day_weather_text_unknown_city_returns_error():
    text = await fetch_3day_weather_text("不存在市")
    assert "找不到" in text


async def test_fetch_3day_weather_text_missing_api_key_returns_setup_message(mocker):
    mocker.patch("bot.weather.CWA_API_KEY", None)
    text = await fetch_3day_weather_text("臺北市")
    assert "CWA_API_KEY" in text


async def test_fetch_3day_weather_text_formats_bucket_with_worst_pop(mocker, mock_async_client):
    mocker.patch("bot.weather.CWA_API_KEY", "key")
    data = {
        "records": {
            "Locations": [
                {
                    "Location": [
                        {
                            "WeatherElement": [
                                {
                                    "ElementName": "天氣現象",
                                    "Time": [
                                        {"StartTime": "2026-08-14T09:00:00", "ElementValue": [{"Weather": "多雲"}]}
                                    ],
                                },
                                {
                                    "ElementName": "溫度",
                                    "Time": [{"DataTime": "2026-08-14T09:00:00", "ElementValue": [{"Temperature": "28"}]}],
                                },
                                {
                                    "ElementName": "3小時降雨機率",
                                    "Time": [
                                        {
                                            "StartTime": "2026-08-14T09:00:00",
                                            "ElementValue": [{"ProbabilityOfPrecipitation": "20"}],
                                        }
                                    ],
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    }
    mock_async_client.get.return_value = FakeResponse(data)

    text = await fetch_3day_weather_text("臺北市")

    expected_weekday = WEEKDAY_NAMES[date(2026, 8, 14).weekday()]
    assert f"08/14（週{expected_weekday}）白天" in text
    assert "多雲" in text
    assert "28°C - 28°C" in text
    assert "降雨機率 20%" in text


async def test_fetch_3day_weather_text_missing_pop_shows_placeholder(mocker, mock_async_client):
    mocker.patch("bot.weather.CWA_API_KEY", "key")
    data = {
        "records": {
            "Locations": [
                {
                    "Location": [
                        {
                            "WeatherElement": [
                                {
                                    "ElementName": "天氣現象",
                                    "Time": [
                                        {"StartTime": "2026-08-14T09:00:00", "ElementValue": [{"Weather": "多雲"}]}
                                    ],
                                },
                                {"ElementName": "溫度", "Time": []},
                                {
                                    "ElementName": "3小時降雨機率",
                                    "Time": [
                                        {
                                            "StartTime": "2026-08-14T09:00:00",
                                            "ElementValue": [{"ProbabilityOfPrecipitation": "-"}],
                                        }
                                    ],
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    }
    mock_async_client.get.return_value = FakeResponse(data)

    text = await fetch_3day_weather_text("臺北市")

    assert "資料未提供" in text


# ---- fetch_weekly_weather_text ----------------------------------------------


async def test_fetch_weekly_weather_text_unknown_city_returns_error():
    text = await fetch_weekly_weather_text("不存在市")
    assert "找不到" in text


async def test_fetch_weekly_weather_text_missing_api_key_returns_setup_message(mocker):
    mocker.patch("bot.weather.CWA_API_KEY", None)
    text = await fetch_weekly_weather_text("臺北市")
    assert "CWA_API_KEY" in text


async def test_fetch_weekly_weather_text_formats_period(mocker, mock_async_client):
    mocker.patch("bot.weather.CWA_API_KEY", "key")
    data = {
        "records": {
            "Locations": [
                {
                    "Location": [
                        {
                            "WeatherElement": [
                                {
                                    "ElementName": "天氣現象",
                                    "Time": [
                                        {"StartTime": "2026-08-14T06:00:00", "ElementValue": [{"Weather": "晴時多雲"}]}
                                    ],
                                },
                                {"ElementName": "最高溫度", "Time": [{"ElementValue": [{"MaxTemperature": "32"}]}]},
                                {"ElementName": "最低溫度", "Time": [{"ElementValue": [{"MinTemperature": "26"}]}]},
                                {
                                    "ElementName": "12小時降雨機率",
                                    "Time": [{"ElementValue": [{"ProbabilityOfPrecipitation": "30"}]}],
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    }
    mock_async_client.get.return_value = FakeResponse(data)

    text = await fetch_weekly_weather_text("臺北市")

    expected_weekday = WEEKDAY_NAMES[date(2026, 8, 14).weekday()]
    assert f"08/14（週{expected_weekday}）白天" in text
    assert "晴時多雲" in text
    assert "26°C - 32°C" in text
    assert "降雨機率 30%" in text


async def test_fetch_weekly_weather_text_dash_pop_shows_placeholder(mocker, mock_async_client):
    mocker.patch("bot.weather.CWA_API_KEY", "key")
    data = {
        "records": {
            "Locations": [
                {
                    "Location": [
                        {
                            "WeatherElement": [
                                {
                                    "ElementName": "天氣現象",
                                    "Time": [
                                        {"StartTime": "2026-08-14T06:00:00", "ElementValue": [{"Weather": "晴時多雲"}]}
                                    ],
                                },
                                {"ElementName": "最高溫度", "Time": [{"ElementValue": [{"MaxTemperature": "32"}]}]},
                                {"ElementName": "最低溫度", "Time": [{"ElementValue": [{"MinTemperature": "26"}]}]},
                                {
                                    "ElementName": "12小時降雨機率",
                                    "Time": [{"ElementValue": [{"ProbabilityOfPrecipitation": "-"}]}],
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    }
    mock_async_client.get.return_value = FakeResponse(data)

    text = await fetch_weekly_weather_text("臺北市")

    assert "資料未提供" in text
