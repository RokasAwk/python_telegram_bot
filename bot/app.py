from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    InlineQueryHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from .basic_commands import help_command, rename, social_media, start
from .callbacks import error_handler, handle_callback_query
from .config import BOT_TOKEN, logger
from .duel import ATTACK_CALLBACK_DATA, attack_command, handle_attack_callback, stop_command
from .guess_1a2b import guess_1a2b_command, stop_1a2b_command
from .guess_number import guess_command, stop_guess_command
from .mrt import (
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
from .net import KEEPALIVE_SOCKET_OPTIONS
from .ooxx import (
    handle_ooxx_again_callback,
    handle_ooxx_move_callback,
    ooxx_command,
    stop_ooxx_command,
)
from .sudoku import handle_sudoku_web_app_data, stop_sudoku_command, sudoku_command
from .text_dispatch import handle_text
from .translate import handle_translate_inline_query, trans_en_command, trans_jp_command
from .thsr import (
    handle_thsrfare_dest_callback,
    handle_thsrfare_origin_callback,
    handle_thsrtime_dest_callback,
    handle_thsrtime_origin_callback,
    thsrfare,
    thsrtime,
)
from .weather import handle_weather_city_callback, handle_weather_period_callback, weather

# 顯示在 Telegram 輸入框旁「/」選單裡的指令說明，跟 chat_rules.rule_capability 的介紹保持一致
BOT_COMMANDS = [
    BotCommand("start", "跟我打招呼"),
    BotCommand("rename", "改變我對你的稱呼"),
    BotCommand("help", "顯示常用問句選單"),
    BotCommand("social_media", "壽司狼哥哥的社群連結"),
    BotCommand("weather", "查詢台灣各縣市天氣"),
    BotCommand("mrt", "查詢捷運車站出入口資訊"),
    BotCommand("mrtfare", "查詢捷運兩站間的全票票價"),
    BotCommand("mrttime", "查詢捷運兩站間的行車時間（可跨線）"),
    BotCommand("thsrtime", "查詢高鐵今日時刻表"),
    BotCommand("thsrfare", "查詢高鐵兩站間的全票票價"),
    BotCommand("attack", "攻擊荒野猛獸，開始決鬥"),
    BotCommand("stop", "中止正在進行的決鬥"),
    BotCommand("guessnumber", "跟壽司小狼玩終極密碼猜數字遊戲"),
    BotCommand("stopguess", "中止正在進行的終極密碼遊戲"),
    BotCommand("guess1a2b", "跟壽司小狼玩1A2B猜數字遊戲"),
    BotCommand("stop1a2b", "中止正在進行的1A2B遊戲"),
    BotCommand("ooxx", "跟壽司小狼玩OOXX井字遊戲"),
    BotCommand("stopooxx", "中止正在進行的OOXX遊戲"),
    BotCommand("sudoku", "跟壽司小狼玩數獨"),
    BotCommand("stopsudoku", "收起數獨的開啟按鈕"),
    BotCommand("trans_jp", "翻譯成日文"),
    BotCommand("trans_en", "翻譯成英文"),
]


async def _register_commands(app: Application):
    await app.bot.set_my_commands(BOT_COMMANDS)


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "找不到 BOT_TOKEN，請在同一目錄建立 .env 檔，內容為：\nBOT_TOKEN=你的token"
        )

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(HTTPXRequest(socket_options=KEEPALIVE_SOCKET_OPTIONS))
        .get_updates_request(
            HTTPXRequest(connection_pool_size=1, socket_options=KEEPALIVE_SOCKET_OPTIONS)
        )
        .post_init(_register_commands)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rename", rename))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("social_media", social_media))
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("mrt", mrt))
    app.add_handler(CommandHandler("mrtfare", mrtfare))
    app.add_handler(CommandHandler("mrttime", mrttime))
    app.add_handler(CommandHandler("thsrtime", thsrtime))
    app.add_handler(CommandHandler("thsrfare", thsrfare))
    app.add_handler(CommandHandler("attack", attack_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("guessnumber", guess_command))
    app.add_handler(CommandHandler("stopguess", stop_guess_command))
    app.add_handler(CommandHandler("guess1a2b", guess_1a2b_command))
    app.add_handler(CommandHandler("stop1a2b", stop_1a2b_command))
    app.add_handler(CommandHandler("ooxx", ooxx_command))
    app.add_handler(CommandHandler("stopooxx", stop_ooxx_command))
    app.add_handler(CommandHandler("sudoku", sudoku_command))
    app.add_handler(CommandHandler("stopsudoku", stop_sudoku_command))
    app.add_handler(CommandHandler("trans_jp", trans_jp_command))
    app.add_handler(CommandHandler("trans_en", trans_en_command))
    # block=False：inline query 會 sleep 做 debounce，不能卡住其他訊息的處理
    app.add_handler(InlineQueryHandler(handle_translate_inline_query, block=False))
    app.add_handler(
        CallbackQueryHandler(handle_attack_callback, pattern=f"^{ATTACK_CALLBACK_DATA}$")
    )
    app.add_handler(CallbackQueryHandler(handle_ooxx_move_callback, pattern=r"^ooxx:move:"))
    app.add_handler(CallbackQueryHandler(handle_ooxx_again_callback, pattern=r"^ooxx:again:"))
    app.add_handler(CallbackQueryHandler(handle_weather_city_callback, pattern=r"^weather:city:"))
    app.add_handler(CallbackQueryHandler(handle_weather_period_callback, pattern=r"^weather:period:"))
    app.add_handler(CallbackQueryHandler(handle_mrt_system_callback, pattern=r"^mrt:system:"))
    app.add_handler(CallbackQueryHandler(handle_mrt_line_callback, pattern=r"^mrt:line:"))
    app.add_handler(CallbackQueryHandler(handle_mrt_station_callback, pattern=r"^mrt:station:"))
    app.add_handler(CallbackQueryHandler(handle_fare_system_callback, pattern=r"^fare:system:"))
    app.add_handler(CallbackQueryHandler(handle_fare_origin_line_callback, pattern=r"^fare:origin_line:"))
    app.add_handler(CallbackQueryHandler(handle_fare_origin_station_callback, pattern=r"^fare:origin_station:"))
    app.add_handler(CallbackQueryHandler(handle_fare_dest_line_callback, pattern=r"^fare:dest_line:"))
    app.add_handler(CallbackQueryHandler(handle_fare_dest_station_callback, pattern=r"^fare:dest_station:"))
    app.add_handler(CallbackQueryHandler(handle_mrttime_system_callback, pattern=r"^mrttime:system:"))
    app.add_handler(CallbackQueryHandler(handle_mrttime_origin_line_callback, pattern=r"^mrttime:oline:"))
    app.add_handler(CallbackQueryHandler(handle_mrttime_origin_station_callback, pattern=r"^mrttime:ostn:"))
    app.add_handler(CallbackQueryHandler(handle_mrttime_dest_line_callback, pattern=r"^mrttime:dline:"))
    app.add_handler(CallbackQueryHandler(handle_mrttime_dest_station_callback, pattern=r"^mrttime:dstn:"))
    app.add_handler(CallbackQueryHandler(handle_thsrtime_origin_callback, pattern=r"^thsrtime:origin:"))
    app.add_handler(CallbackQueryHandler(handle_thsrtime_dest_callback, pattern=r"^thsrtime:dest:"))
    app.add_handler(CallbackQueryHandler(handle_thsrfare_origin_callback, pattern=r"^thsrfare:origin:"))
    app.add_handler(CallbackQueryHandler(handle_thsrfare_dest_callback, pattern=r"^thsrfare:dest:"))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_sudoku_web_app_data))
    # ~VIA_BOT：透過 inline 送出的訊息（例如點了即時翻譯結果送出的日文）是給聊天對象看的，不是在跟 bot 講話，不回覆
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.VIA_BOT, handle_text))
    app.add_error_handler(error_handler)

    logger.info("Bot 啟動中，開始用 long polling 監聽訊息...")
    app.run_polling()
