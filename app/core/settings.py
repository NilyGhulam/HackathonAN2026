from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data" / "demo"
RAW_DATA_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"
SCHEMAS_DIR = BASE_DIR / "data" / "schemas"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"
ASSISTANT_PROMPT_PATH = BASE_DIR / "docs" / "api" / "extraction_prompt.md"
