import logging
import os

import truststore
from dotenv import load_dotenv

# 改用作業系統的憑證信任邏輯，避免某些 OpenSSL 版本對政府機關（如中央氣象署）
# 憑證鏈過於嚴格判讀（缺 Subject Key Identifier）而連線失敗
truststore.inject_into_ssl()

# 讀取 .env 檔裡的環境變數（BOT_TOKEN、CWA_API_KEY、TDX_CLIENT_ID、TDX_CLIENT_SECRET）
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CWA_API_KEY = os.environ.get("CWA_API_KEY")
CWA_DATASTORE_BASE_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"

# TDX（運輸資料流通服務）用 client_credentials 換 access token
TDX_CLIENT_ID = os.environ.get("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.environ.get("TDX_CLIENT_SECRET")
TDX_AUTH_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
TDX_API_BASE_URL = "https://tdx.transportdata.tw/api/basic"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("telegram_bot")

STICKER_ID = "CAACAgUAAxkBAANuYkJtvnLvttU_7vhpqBn3Y7FIIYkAAkcFAAKIOolUbN1l5sfsXuwjBA"
