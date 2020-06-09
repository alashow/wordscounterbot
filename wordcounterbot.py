import config
import re
import actions
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import threading
from datetime import datetime
import utils
import logging
import time

handler = logging.StreamHandler()
# logging.basicConfig(level=logging.DEBUG)

@utils.background
def initStreamListener(workers=100):
	pool = ThreadPoolExecutor(max_workers=workers)
	for comment in config.sub.stream.comments(skip_existing=False):
		pool.submit(actions.processComment, (comment))

def initMentionsListener(workers=10):
	lastSeenKey = "mentions"
	lastSeen = utils.get_last_seen(lastSeenKey)
	
	pool = ThreadPoolExecutor(max_workers=workers)
	mentions = list(config.reddit.inbox.mentions(limit=25))

	utils.set_last_seen(lastSeenKey, mentions[0].created_utc)

	for comment in mentions:
		createdAt = comment.created_utc
		if lastSeen >= utils.datetime_from_timestamp(createdAt):
			break;
		
		print(f"Processing mention by u/{comment.author}: {comment.body}, {createdAt}")
		if comment.new:
			pool.submit(comment.mark_read)
			pool.submit(actions.processComment, (comment))

initStreamListener()

while True:
	initMentionsListener()
	time.sleep(1)