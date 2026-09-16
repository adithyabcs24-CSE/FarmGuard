import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from project root
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)
else:
    load_dotenv()

STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = STATIC_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Application Settings
APP_NAME = os.getenv("APP_NAME", "FarmGuard AI")
APP_ENV = os.getenv("APP_ENV", "development")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

# Security & Authentication
SECRET_KEY = os.getenv("SECRET_KEY", "farmguard-ai-secure-secret-key-2026")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))  # 7 days

# Database & External Services
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/farmguard.db")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
DEFAULT_ADVISORY_LANGUAGE = os.getenv("DEFAULT_ADVISORY_LANGUAGE", "English")

