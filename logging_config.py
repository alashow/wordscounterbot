import logging
import logging.config
from config import env

DEFAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    "handlers": {
        "telegram": {
            "class": "python_telegram_logger.Handler",
            "token": env('TELEGRAM_LOG_BOT_TOKEN', ""),
            "chat_ids": list(map(int, env('TELEGRAM_LOG_CHAT_ID', "0").split(','))),
        }
    },
    'loggers': {
        '': {
            'level': 'INFO',
        },
        "tg": {
            "level": "INFO",
            "handlers": ["telegram",]
        }
    }
}

logging.config.dictConfig(DEFAULT_LOGGING)

tgLogger = logging.getLogger("tg")