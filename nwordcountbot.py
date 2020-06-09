import config
import re
import actions
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import threading
import utils
from reddit_utils import RedditKeywordWatcher

# import logging

# handler = logging.StreamHandler()
# handler.setLevel(logging.DEBUG)
# for logger_name in ("praw", "prawcore"):
#     logger = logging.getLogger(logger_name)
#     logger.setLevel(logging.DEBUG)
#     logger.addHandler(handler)

pool = ThreadPoolExecutor(max_workers=100)

botname = "nwordcountbot"
watcher = RedditKeywordWatcher(botname)

while True:
	for c in watcher.get():
		id = c['id']
		pool.submit(actions.processCommentById, (id))
		watcher.set_processed(id)
		utils.set_last_seen(botname, c['created_utc'])