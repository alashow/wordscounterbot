import logging
import logging.config

DEFAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'loggers': {
        '': {
            'level': 'INFO',
        },
        'another.module': {
            'level': 'DEBUG',
        },
    }
}

logging.config.dictConfig(DEFAULT_LOGGING)