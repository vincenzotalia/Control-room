import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _parse_bool(raw_value: str | None, default: bool) -> bool:
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(raw_value: str | None, default: Path) -> Path:
    if not raw_value:
        return default.resolve()

    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate.resolve()


APP_ENV = (os.getenv("WCR_ENV") or "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"production", "prod", "staging"}

STORAGE_ROOT = _resolve_path(os.getenv("WCR_STORAGE_ROOT"), BASE_DIR)
UPLOAD_ROOT = _resolve_path(os.getenv("WCR_UPLOAD_ROOT"), STORAGE_ROOT / "uploads" / "area_manager")
CACHE_ROOT = _resolve_path(os.getenv("WCR_CACHE_ROOT"), STORAGE_ROOT / ".runtime-cache")
DATA_ROOT = _resolve_path(os.getenv("WCR_DATA_ROOT"), STORAGE_ROOT / "data")
DATA_INPUT_DIR = _resolve_path(os.getenv("WCR_DATA_INPUT_DIR"), DATA_ROOT / "input")
DATA_HISTORY_DIR = _resolve_path(os.getenv("WCR_DATA_HISTORY_DIR"), DATA_ROOT / "history")

ALERT_HUB_DB_PATH = _resolve_path(os.getenv("WCR_ALERT_HUB_DB_PATH"), STORAGE_ROOT / "alert_hub.db")
AREA_MANAGER_DB_PATH = _resolve_path(os.getenv("WCR_AREA_MANAGER_DB_PATH"), STORAGE_ROOT / "area_manager.db")

HOST = (os.getenv("WCR_HOST") or "0.0.0.0").strip()
PORT = int((os.getenv("PORT") or os.getenv("WCR_PORT") or "8000").strip())
RELOAD = _parse_bool(os.getenv("WCR_RELOAD"), default=not IS_PRODUCTION)
FILE_STORAGE_BACKEND = (os.getenv("WCR_FILE_STORAGE_BACKEND") or "local").strip().lower()
AZURE_BLOB_CONNECTION_STRING = (os.getenv("AZURE_STORAGE_CONNECTION_STRING") or "").strip()
AZURE_BLOB_CONTAINER = (os.getenv("WCR_BLOB_CONTAINER") or "warehouse-control-room").strip()


def _get_pin(var_name: str, dev_default: str) -> str:
    value = (os.getenv(var_name) or "").strip()
    if value:
        return value
    if IS_PRODUCTION:
        raise RuntimeError(f"{var_name} must be set when WCR_ENV={APP_ENV}")
    return dev_default


ALERT_HUB_PIN = _get_pin("WCR_ALERT_HUB_PIN", "4839")
AREA_MANAGER_PIN = _get_pin("WCR_AREA_MANAGER_PIN", ALERT_HUB_PIN)


def get_cors_origins() -> list[str]:
    raw_value = (os.getenv("WCR_CORS_ORIGINS") or "*").strip()
    if raw_value == "*":
        return ["*"]
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]
