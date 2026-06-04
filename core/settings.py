# --- START OF FILE core/settings.py ---
import os
import sys
import yaml
from typing import List, Union, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    SUBSCRIPTION_SOURCES: Union[str, List[str]] = []
    TG_BOT_TOKEN: str = ""
    TG_CHAT_ID: str = ""
    TG_TOPIC_ID: str = ""

    parser: Dict[str, Any] = {}
    system: Dict[str, Any] = {}
    checking: Dict[str, Any] = {}
    app: Dict[str, Any] = {}
    whitelist: Dict[str, Any] = {}
    BATCH_SIZE: int = 100
    CHAMPION_TOP_N: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


def load_settings() -> AppSettings:
    yaml_path = "config/settings.yaml"
    yaml_data: Dict[str, Any] = {}

    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}
        except Exception as e:
            print(
                f"FATAL: Сбой парсинга YAML конфигурации. Дальнейшая работа невозможна. Ошибка: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        settings = AppSettings(**yaml_data)
    except Exception as e:
        print(
            f"FATAL: Сбой валидации конфигурации: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    return settings


CONFIG = load_settings()
