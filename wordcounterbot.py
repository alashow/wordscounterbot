import config
import re
import actions
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import threading
from datetime import datetime
import utils
import logging
import logging.config
import time
from praw.models import Comment

def checkUnreadMessages(workers=10):
	lastSeenKey = "messages"
	lastSeen = utils.get_last_seen(lastSeenKey)
	lastMessageAt = utils.get_last_seen(lastSeenKey, True);
	
	inbox = config.reddit.inbox
	pool = ThreadPoolExecutor(max_workers=workers)
	messages = list(inbox.unread(limit=None))

	for item in messages:
		isComment = isinstance(item, Comment)

		createdAt = item.created_utc
		if lastSeen >= utils.datetime_from_timestamp(createdAt):
			break;

		if createdAt > lastMessageAt:
			logging.info(f"Found new last message: {utils.datetime_from_timestamp(createdAt)}")
			lastMessageAt = createdAt;

		if item.new:
			logging.info(f"Sending unread item to be processed: itemCreatedAt={createdAt}")
			pool.submit(actions.processUnreadItem, (item))
	
	if messages:
		utils.set_last_seen(lastSeenKey, lastMessageAt)
		inbox.mark_read(messages)

while True:
	try:
		checkUnreadMessages()
		time.sleep(5)
	except Exception as e:
		logging.info(f"Caught exception while checking unread messages: {e}")