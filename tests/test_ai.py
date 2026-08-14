from unittest.mock import AsyncMock, MagicMock

from google.genai import errors

from bot.ai import MODEL_NAME, QUOTA_EXCEEDED_REPLY, ask_ai


async def test_ask_ai_returns_none_when_client_not_configured(mocker):
    mocker.patch("bot.ai._client", None)

    assert await ask_ai("哈囉", "小明") is None


async def test_ask_ai_returns_response_text_on_success(mocker):
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=MagicMock(text="回覆內容"))
    mocker.patch("bot.ai._client", mock_client)

    result = await ask_ai("哈囉", "小明")

    assert result == "回覆內容"
    call = mock_client.aio.models.generate_content.call_args
    assert call.kwargs["model"] == MODEL_NAME
    assert call.kwargs["contents"] == "小明：哈囉"


async def test_ask_ai_returns_quota_reply_on_429(mocker):
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=errors.ClientError(429, {}))
    mocker.patch("bot.ai._client", mock_client)

    result = await ask_ai("哈囉", "小明")

    assert result == QUOTA_EXCEEDED_REPLY


async def test_ask_ai_returns_none_on_other_client_error(mocker):
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=errors.ClientError(400, {}))
    mocker.patch("bot.ai._client", mock_client)
    logger_mock = mocker.patch("bot.ai.logger")

    result = await ask_ai("哈囉", "小明")

    assert result is None
    logger_mock.exception.assert_called_once()


async def test_ask_ai_returns_none_on_unexpected_exception(mocker):
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("boom"))
    mocker.patch("bot.ai._client", mock_client)
    logger_mock = mocker.patch("bot.ai.logger")

    result = await ask_ai("哈囉", "小明")

    assert result is None
    logger_mock.exception.assert_called_once()
