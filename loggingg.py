import logging
from logging.handlers import TimedRotatingFileHandler
import os
from datetime import datetime

def get_logger():
    # Singleton logger
    logger = logging.getLogger("BotLogger")
    logger.setLevel(logging.INFO)

    # ❌ Prevent duplicate handlers
    if logger.handlers:
        return logger

    # 📁 Log folder
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    os.makedirs(LOG_DIR, exist_ok=True)

    # 🔹 Daily log file name
    today_date = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"bot_{today_date}.log")

    # 🔹 TimedRotatingFileHandler (auto rotate next day, keep 7 backups)
    handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
        utc=False
    )

    # Optional: attach suffix for safety (filename with date)
    handler.suffix = "%Y-%m-%d"

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)

    # Add handler
    logger.addHandler(handler)

    return logger

