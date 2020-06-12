import config
import actions
from concurrent.futures import ThreadPoolExecutor
import utils
import logging

processed = 0
@utils.background
def initStreamListener(workers=100):
	global processed
	
	pool = ThreadPoolExecutor(max_workers=workers)
	for comment in config.sub.stream.comments(skip_existing=False):
		processed += 1
		print(f"Sending streaming comment to be processed: {comment.id}, {processed}")
		pool.submit(actions.processComment, (comment))

try:
	initStreamListener()
except:
	initStreamListener()