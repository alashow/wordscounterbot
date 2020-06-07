import config
import re
import actions
import logging
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import threading


# handler = logging.StreamHandler()
# handler.setLevel(logging.DEBUG)
# for logger_name in ("praw", "prawcore"):
#     logger = logging.getLogger(logger_name)
#     logger.setLevel(logging.DEBUG)
#     logger.addHandler(handler)

pool = ThreadPoolExecutor(max_workers=10)
for comment in config.sub.stream.comments(skip_existing=False):
	pool.submit(actions.processGlobalComment, (comment))