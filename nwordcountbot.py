import config
from actions import processComment
import time

sleepSecondsBetweenChecks = 30

def processRecentNwordCalls(max_skips=2):
	print('Getting recent nwordcountbot calls')
	comments = list(config.apiReddit.search_comments(q="nwordcountbot", filter=['body', 'replies'], limit=500))
	skipped = 0
	for c in comments:
		if not processComment(c):
			skipped += 1
		if skipped > max_skips:
			print('Reached max skips of processing recent comments.')
			break

while True:
	processRecentNwordCalls()
	print('Sleeping for %d seconds before next check' % (sleepSecondsBetweenChecks))
	time.sleep(sleepSecondsBetweenChecks)