"""App key and secret."""

import os

# --- credentials: injected at build time via scripts/update_credentials.py — do not edit ---
APP_KEY: str = ""
APP_SECRET: str = ""
MAMMOTION_OUATH2_CLIENT_ID: str = ""
MAMMOTION_OUATH2_CLIENT_SECRET: str = ""
# --- end credentials ---

if not APP_KEY:
    from dotenv import load_dotenv

    load_dotenv()
    APP_KEY = os.environ.get("ALIYUN_APP_KEY", "34231230")
    APP_SECRET = os.environ.get("ALIYUN_APP_SECRET", "1ba85698bb10e19c6437413b61ba3445")

if not MAMMOTION_OUATH2_CLIENT_ID:
    MAMMOTION_OUATH2_CLIENT_ID = os.environ.get("MAMMOTION_OAUTH2_CLIENT_ID", "")
    MAMMOTION_OUATH2_CLIENT_SECRET = os.environ.get("MAMMOTION_OAUTH2_CLIENT_SECRET", "")

APP_VERSION = "2.3.2.13"
ALIYUN_DOMAIN = "api.link.aliyun.com"
MAMMOTION_DOMAIN = "https://id.mammotion.com"
MAMMOTION_API_DOMAIN = "https://domestic.mammotion.com"
MAMMOTION_CLIENT_ID = "MADKALUBAS"
MAMMOTION_CLIENT_SECRET = "GshzGRZJjuMUgd2sYHM7"
