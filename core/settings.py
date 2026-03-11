import os
import sys
import yaml
from typing import List, Union, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    SUBSCRIPTION_SOURCES: Union[str, List[str]] =[]
    TG_BOT_TOKEN: str = ""
    TG_CHAT_ID: str = ""
    TG_TOPIC_ID: str = ""

    parser: Dict[str, Any] = {}
    system: Dict[str, Any] = {}
    checking: Dict[str, Any] = {}
    app: Dict[str, Any] = {}
    whitelist: Dict[str, Any] = {}
    BATCH_SIZE: int = 100

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

def load_settings() -> AppSettings:
    settings = AppSettings()
    yaml_path = "config/settings.yaml"
    
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}
                
            for key, value in yaml_data.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)
        except Exception as e:
            print(f"FATAL: Сбой парсинга YAML конфигурации. Дальнейшая работа невозможна. Ошибка: {e}", file=sys.stderr)
            sys.exit(1)
            
    return settings

CONFIG = load_settings()
