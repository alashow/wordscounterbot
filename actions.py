import logging
import config
import utils
import re
import praw
import threading 
from rq import Queue
from datetime import datetime
from datetime import timedelta
from durations import Duration
from utils import background
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

def isUserBlacklisted(user):
	return user in config.TARGET_USER_BLACKLIST

def processComment(comment):
	commentBody = comment.body
	commentBody = utils.markdownToText(commentBody)
	match = re.search(r"(u\/({botname}|nwordcountbot)) ?(u\/[a-zA-Z0-9-_]{{1,100}})? ?(\'(.*){{1,100}}\')?".format(botname=config.BOTNAME), commentBody)

	if match and match.group(1):
		thread = threading.Thread(target=processSummoning, args=[comment, ("nword" in match.group(1)), match.group(3), match.group(4)])
		thread.start()

def processSummoning(comment, isNwords, targetUser, targetWords):
	state = config.state
	inflight = f"inflight_{comment.id}"

	if state.get(inflight):
		logging.debug(f"Skipping already inflight comment from processing: {comment.id}")
		return;

	state.set(inflight, True)
	print(f"Processing summoning by u/{comment.author}: {comment.body}")

	targetUser = targetUser or "u/%s" % comment.parent().author
	targetWords = config.DEFAULT_TARGET_WORDS if (targetWords is None) else (targetWords[1:-1].split(','))
	targetWords = config.N_WORDS if isNwords else targetWords
	hasTargetUser = not (targetUser is None)

	if hasTargetUser:
		targetUser = targetUser[2:]
		if isUserBlacklisted(targetUser):
			print(f"Skipping blacklisted user {targetUser}")
			return
		print(f"Analyzing user u/{targetUser} for word(s):  {', '.join(targetWords)}")
		count, countNR = analyzeUser(targetUser, targetWords, comment)
		logging.debug(f"Finished analyzing user u/{targetUser}, results: {count}, {countNR}")
		replyToComment(comment, targetUser, targetWords, count, countNR)

	state.rem(inflight)

def analyzeUser(targetUser, targetWords=config.N_WORDS, comment = None):
	isNwords = targetWords == config.N_WORDS

	submissions = getUserPosts(targetUser)
	recentComments = list(config.reddit.redditor(targetUser).comments.new())
	comments = list(config.api.search_comments(author=targetUser, filter=['body'], before=int(recentComments[-1].created_utc), q="|".join(targetWords), size=1000))

	totalMatches = 0
	totalNRMatches = 0

	for s in submissions:
		totalMatches += countTextForWords(targetWords, s.title) + countTextForWords(targetWords, s.selftext) if(hasattr(s, 'selftext')) else 0
		if isNwords:
			totalNRMatches += countTextForWords(targetWords[1:], s.title) + countTextForWords(targetWords[1:], s.selftext) if(hasattr(s, 'selftext')) else 0
	for c in recentComments:
		totalMatches += countTextForWords(targetWords, c.body)
		if isNwords:
			totalNRMatches += countTextForWords(targetWords[2:], c.body)			
	for c in comments:
		totalMatches += countTextForWords(targetWords, c.body)
		if isNwords:
			totalNRMatches += countTextForWords(targetWords[2:], c.body)

	return totalMatches, totalNRMatches

def countTextForWords(words, text):
	pattern = r"({q})".format(q='|'.join(words))
	return len(re.findall(pattern, text.lower()))

def replyToComment(comment, targetUser, targetWords, count, countNR):
	saveCount(comment, targetUser, targetWords, count, countNR)

	replyText = utils.buildCounterReplyComment(targetUser, targetWords, count, countNR);
	print("Will try to comment to reply with: %s " % replyText)
	try:
		post = comment.submission
		if post and (post.locked or post.archived):
			print("Post is locked or archived")
		reply = comment.reply(replyText)
		print(f"Successfully replied: {utils.linkify(reply)}")
	except praw.exceptions.RedditAPIException as e:
		for error in e.items:
			match = re.search(r"(try again in )([0-9a-zA-z ]{1,15})\.", error.message)
			if match and match.group(2):
				duration = Duration(match.group(2)).to_seconds()
				print(f"Couldn't reply because of rate limit so scheduled it to reply in {duration} seconds")
				queue = Queue(connection=utils.redis())
				queue.enqueue_in(timedelta(seconds=duration), replyToComment, comment, targetUser, targetWords, count, countNR)
	except Exception as e:
		# todo: maybe send it to the author of the comment?
		print(f"Couldn't recover from error: {e}")

def processCommentWithCheck(comment):
	comment.refresh()
	alreadyReplied = False
	for c in comment.replies:
		if c.author == config.BOTNAME:
			loggind.debug(f"Already replied to comment {comment.id} with comment {utils.linkify(c)}")
			alreadyReplied = True
			break
	if not alreadyReplied:
		print(f"Will process comment by '{comment.author}': {comment.body}, {utils.linkify(comment)}")
		processComment(comment)
		return True
	else:
		logging.debug(f"Skipping already processed comment: {utils.linkify(comment)}" )
		return False

def processCommentById(id):
	return processCommentWithCheck(getCommentById(id))

def processPostComments(post=None, id=None, workers=10):
	if post and (post.locked or post.archived):
		print("Post is locked or archived, skipping")
		return

	comments = getPostComments(post=post) if post else getPostComments(id=id)
	pool = ThreadPoolExecutor(max_workers=workers)
	for comment in tqdm(comments, "Processing post comments"):
		pool.submit(processComment, (comment))

def processUserCommentParents(user):
	redditor = config.reddit.redditor(user)
	comments = getUserComments(redditor.name)

	for c in tqdm(comments, "Processing user comments"):
		parent = c.parent()
		if parent.is_root:
			processPostComments(post=parent.parent())
		else:
			parent.replies.replace_more(limit=None)
			for x in parent.replies.list():
				processComment(x)

def getCommentById(id):
	return config.reddit.comment(id=id)

def getPostComments(post=None, id=None):
	post = post or config.reddit.submission(id=id)
	post.comments.replace_more(limit=None)
	return post.comments.list()

def getUserComments(user, fields=['body']):
	recentComments = list(config.reddit.redditor(user).comments.new())
	comments = list(config.api.search_comments(author=user, filter=body, before=int(recentComments[-1].created_utc), size=1000))

	return recentComments+comments

def getUserPosts(user, fields=['selftext', 'title', 'id']):
	return list(config.api.search_submissions(author=user, filter=fields, size=500))

def getSaveKey(targetUser, targetWords):
	return f"{targetUser}.{b64encode(str(targetWords).encode('utf-8')).decode('utf-8')}"

@background
def saveCount(comment, targetUser, targetWords, count, countNR):
	key = getSaveKey(targetUser, targetWords)
	config.db.set(key, {"count": count, "countNR": countNR})
	config.db.dump()
	print(f"Saved count for: {key}")