import logging
import config
import utils
import re
import praw
from rq import Queue
from datetime import timedelta
from durations import Duration
import threading

def isUserBlacklisted(user):
	return user in config.TARGET_USER_BLACKLIST

def processGlobalComment(comment):
	commentBody = comment.body
	commentBody = utils.markdownToText(commentBody)
	match = re.search(r"(u\/({botname}|nwordcountbot)) ?(u\/[a-zA-Z0-9-_]{{1,100}})? ?(.*){{1,100}}?".format(botname=config.BOTNAME), commentBody)

	if match and match.group(1):
		thread = threading.Thread(target=processSummoning, args=[comment, ("nword" in match.group(1)), match.group(3), match.group(4)])
		thread.start()

def processSummoning(comment, isNwords, targetUser, targetWords):
	print("Processing summoning by '%s': %s" % (comment.author, comment.body))
	targetUser = targetUser or "u/%s" % comment.parent().author
	targetWords = config.N_WORDS if isNwords else (targetWords.split() or config.DEFAULT_TARGET_WORDS)
	hasTargetUser = not (targetUser is None)

	if hasTargetUser:
		targetUser = targetUser[2:]
		if isUserBlacklisted(targetUser):
			print("Skipping blacklisted user %s" % targetUser)
			return
		print("Analyzing user %s for word(s) %s " % (targetUser, ', '.join(targetWords)))
		count, countNR = analyzeUser(targetUser, targetWords)
		replyToComment(comment, targetUser, targetWords, count, countNR)

def analyzeUser(targetUser, targetWords):
	submissions = list(config.api.search_submissions(author=targetUser, filter=['selftext', 'title', 'id'], size=500))
	recentComments = list(config.reddit.redditor(targetUser).comments.new())
	comments = list(config.api.search_comments(author=targetUser, filter=['body'], before=int(recentComments[-1].created_utc), size=500))
	isNwords = targetWords == config.N_WORDS
	
	totalMatches = 0
	totalNRMatches = 0
	for s in submissions:
		totalMatches += countTextForWords(targetWords, s.title) + countTextForWords(targetWords, s.selftext) if(hasattr(s, 'selftext')) else 0
		if isNwords:
			totalNRMatches += countTextForWords(targetWords[1:], s.title) + countTextForWords(targetWords[1:], s.selftext) if(hasattr(s, 'selftext')) else 0
	for c in (recentComments+comments):
		totalMatches += countTextForWords(targetWords, c.body)
		if isNwords:
			totalNRMatches += countTextForWords(targetWords[1:], c.body)

	return totalMatches, totalNRMatches

def countTextForWords(words, text):
	pattern = r"({q})".format(q='|'.join(words))
	return len(re.findall(pattern, text.lower()))

def replyToComment(comment, targetUser, targetWords, count, countNR):
	replyText = utils.buildCounterReplyComment(targetUser, targetWords, count, countNR);
	print("Will try to comment to reply with: %s " % replyText)
	try:
		reply = comment.reply(replyText)
		print("Successfully replied: %s" % utils.linkify(reply))
	except praw.exceptions.RedditAPIException as e:
		for error in e.items:
			match = re.search(r"(try again in )([0-9a-zA-z ]{1,15})\.", error.message)
			if match and match.group(2):
				duration = Duration(match.group(2)).to_seconds()
				print("Couldn't reply because of rate limit so scheduled it to reply in %d seconds" % duration)
				queue = Queue(connection=utils.redis())
				queue.enqueue_in(timedelta(seconds=duration), replyToComment, comment, targetUser, targetWords, count, countNR)
			else:
				# todo: maybe send it to the author of the comment?
				print("Couldn't recover from error: %s " % error.message)

def processComment(comment):
	comment.refresh()
	alreadyReplied = False
	for c in comment.replies:
		if c.author == config.BOTNAME:
			print('Already replied to comment %s with comment %s' % (comment.id, utils.linkify(c)))
			alreadyReplied = True
			break
	if not alreadyReplied:
		print("Will process comment by '%s': %s" % (comment.author, comment.body))
		processGlobalComment(comment)
		return True
	else:
		print("Skipping already processed comment by '%s': %s" % (comment.author, comment.body))
		return False

def processCommentById(id):
	return processComment(getCommentById(id))

def getCommentById(id):
	return config.reddit.comment(id=id)