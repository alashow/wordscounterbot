import logging
import config
import utils
import re
import praw
from rq import Queue
from datetime import timedelta
from durations import Duration

def isUserBlacklisted(user):
	return user in config.TARGET_USER_BLACLIST

def processGlobalComment(comment):
	# logging.info("Processing comment: %s" % comment.body)
	commentBody = comment.body
	commentBody = utils.markdownToText(commentBody)
	match = re.search(r"(u\/({botname}|nwordcountbot)) ?(u\/[a-zA-Z-_]{{1,100}})? ?(.*){{1,100}}?".format(botname=config.BOTNAME), commentBody)

	if match and match.group(1):
		queue = Queue(connection=utils.redis())
		queue.enqueue(processSummoning, comment, match.group(3), match.group(4))
	else:
		logging.info("No match for comment %s" % comment.body)

def processSummoning(comment, targetUser, targetWords):
	logging.info("Processing summoning %s" % comment.body)
	targetUser = targetUser or "u/%s" % comment.parent().author
	targetWords = targetWords.split() or config.DEFAULT_TARGET_WORDS
	hasTargetUser = not (targetUser is None)

	if hasTargetUser:
		targetUser = targetUser[2:]
		if isUserBlacklisted(targetUser):
			print("Skipping blacklisted user %s" % targetUser)
			return
		print("Analyzing user %s for word(s) %s " % (targetUser, ', '.join(targetWords)))
		count = analyzeComments(targetUser, targetWords)
		replyToComment(comment, targetUser, targetWords, count)

def analyzeComments(targetUser, targetWords):
	totalMatches = 0
	results = list(config.api.search_comments(author=targetUser, filter=['body'], size=500))
	for comment in results:
		commentBody = comment.body
		pattern = r"({q})".format(q='|'.join(targetWords))
		totalMatches += len(re.findall(pattern, commentBody.lower()))
	return totalMatches

def replyToComment(comment, targetUser, targetWords, count):
	replyText = utils.buildCounterReplyComment(targetUser, count, targetWords);
	print("Will try to comment to reply with %s " % replyText)
	try:
		comment.reply(replyText)
	except praw.exceptions.RedditAPIException as e:
		for error in e.items:
			match = re.search(r"(try again in )([0-9a-zA-z ]{1,15})\.", error.message)
			if match.group(2):
				duration = Duration(match.group(2)).to_seconds()
				print("Couldn't reply because of rate limit so scheduled it to reply in %d seconds" % duration)
				queue = Queue(connection=utils.redis())
				queue.enqueue_in(timedelta(seconds=duration), replyToComment, comment, targetUser, targetWords, count)