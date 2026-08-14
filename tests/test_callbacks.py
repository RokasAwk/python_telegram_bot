from unittest.mock import MagicMock

from bot.callbacks import error_handler, handle_callback_query


async def test_handle_callback_query_answers_the_query(make_callback_update, make_context):
    update = make_callback_update("anything")

    await handle_callback_query(update, make_context())

    update.callback_query.answer.assert_awaited_once()


async def test_error_handler_logs_the_exception(mocker):
    logger_mock = mocker.patch("bot.callbacks.logger")
    context = MagicMock()
    context.error = ValueError("boom")

    await error_handler(None, context)

    logger_mock.error.assert_called_once()
    _, kwargs = logger_mock.error.call_args
    assert kwargs["exc_info"] is context.error
