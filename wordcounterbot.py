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
from praw.models import Comment

handler = logging.StreamHandler()
# logging.basicConfig(level=logging.DEBUG)

@utils.background
def initStreamListener(workers=100):
	pool = ThreadPoolExecutor(max_workers=workers)
	for comment in config.sub.stream.comments(skip_existing=False):
		pool.submit(actions.processComment, (comment))

def checkUnreadMessages(workers=10):
	lastSeenKey = "messages"
	lastSeen = utils.get_last_seen(lastSeenKey)
	lastMessageAt = utils.get_last_seen(lastSeenKey, True);
	
	inbox = config.reddit.inbox
	pool = ThreadPoolExecutor(max_workers=workers)
	messages = list(inbox.unread(limit=25))

	for item in messages:
		isComment = isinstance(item, Comment)

		createdAt = item.created_utc
		if lastSeen >= utils.datetime_from_timestamp(createdAt):
			break;

		if createdAt > lastMessageAt:
			print(f"Found new last message: {utils.datetime_from_timestamp(createdAt)}")
			lastMessageAt = createdAt;
		
		print(f"Processing message by u/{item.author}: {item.body}, {createdAt}")
		if item.new:
			pool.submit(actions.processComment if isComment else actions.processMessage, (item))
	
	if messages:
		utils.set_last_seen(lastSeenKey, lastMessageAt)
		inbox.mark_read(messages)

initStreamListener()

while True:
	checkUnreadMessages()
	time.sleep(5)