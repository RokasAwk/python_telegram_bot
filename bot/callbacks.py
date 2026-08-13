from telegram import Update
from telegram.ext import ContextTypes

from .config import logger


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """統一處理未預期的錯誤，避免 bot 因為單一錯誤整個掛掉"""
    logger.error("發生例外：", exc_info=context.error)
