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
from classes.queue import Queue

def isUserBlacklisted(user):
	return user in config.TARGET_USER_BLACKLIST

# returns False if no match or (botname, username, words, withLinks)
def parseCommandText(body):
	text = utils.markdownToText(body)
	match = re.search(config.COMMAND_PATTERN, text)

	if match and match.group(1):
		words = match.group(5)
		print(match.group())
		words = config.DEFAULT_TARGET_WORDS if (words is None) else words[1:-1].split(',')
		words = config.N_WORDS if "nword" in match.group(1) else words

		return (match.group(2), match.group(4), words, match.group(7)) 
	else:
		return False

def processComment(comment):
	result = parseCommandText(comment.body)
	if result:
		print(result)
		(bot, user, words, withLinks) = result
		thread = threading.Thread(target=processSummoning, args=[comment, user, words, withLinks])
		thread.start()

def processSummoning(comment, user, words, withLinks = False):
	print(comment, user, words)
	state = config.state
	inflight = f"inflight_{comment.id}"

	if state.get(inflight):
		logging.debug(f"Skipping already inflight comment from processing: {comment.id}")
		return;

	state.set(inflight, True)
	print(f"Processing summoning by u/{comment.author}: {comment.body}")

	user = user or comment.parent().author
	if user:
		if isUserBlacklisted(user):
			print(f"Skipping blacklisted user {user}")
			return

		count, countNR, links = analyzeUser(user, words, comment, withLinks)
		replyToComment(comment, user, words, count, countNR, links)

	state.rem(inflight)

def processMessage(message):
	result = parseCommandText(message.body)
	if result:
		(bot, user, words, withLinks) = result
		if user:
			if isUserBlacklisted(user):
				print(f"Skipping blacklisted user {user}")
				return
			count, countNR, links = analyzeUser(user, words, withLinks = withLinks)
			replyToMessage(message, user, words, count, countNR, links)
		else:
			logging.debug("Message didn't have a target body, skipping.")

def analyzeUser(user, words=config.N_WORDS, comment = None, withLinks = False):
	print(f"Analyzing user u/{user} for word(s): {', '.join(words)}")

	isNwords = words == config.N_WORDS
	extraFields = ['permalink'] if withLinks else []
	submissions = getUserPosts(user, extraFields=extraFields)
	recentComments = list(config.reddit.redditor(user).comments.new())
	comments = list(config.api.search_comments(author=user, filter=['body', 'id']+extraFields, q="|".join(words), size=1000))

	totalMatches = 0
	totalNRMatches = 0
	links = []
	for s in submissions:
		count = countTextForWords(words, s.title) + countTextForWords(words, s.selftext) if(hasattr(s, 'selftext')) else 0
		totalMatches += count
		if withLinks and count > 0 and hasattr(s, 'permalink'):
			links.append(s.permalink)
		if isNwords:
			totalNRMatches += countTextForWords(words[2:], s.title) + countTextForWords(words[2:], s.selftext) if(hasattr(s, 'selftext')) else 0
	processedComments = []
	for c in (recentComments+comments):
		if c.id in processedComments:
			continue
		processedComments.append(c.id)

		count = countTextForWords(words, c.body)
		totalMatches += count
		if withLinks and count > 0 and hasattr(c, 'permalink'):
			links.append(c.permalink)
		if isNwords:
			totalNRMatches += countTextForWords(words[2:], c.body)

	logging.debug(f"Finished analyzing user u/{user}, results: {totalMatches}, {totalNRMatches}")
	return totalMatches, totalNRMatches, list(map(lambda x: utils.linkify(x), links))

def countTextForWords(words, text):
	pattern = r"({q})".format(q='|'.join(words))
	return len(re.findall(pattern, text.lower()))

def replyToComment(comment, user, words, count, countNR, links = []):
	saveCount(comment, user, words, count, countNR)

	replyText = utils.buildCounterReply(user, words, count, countNR);
	if links:
		replyText += f"\n\n{utils.prettyLinks(links)}"

	print(f"Will try to comment to reply with: {replyText}")
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
				queue.enqueue_in(timedelta(seconds=duration), replyToComment, comment, user, words, count, countNR)
	except Exception as e:
		# todo: maybe send it to the author of the comment?
		print(f"Couldn't recover from error: {e}")

def replyToMessage(message, user, words, count, countNR, links = []):
	replyText = utils.buildCounterReply(user, words, count, countNR);
	if links:
		replyText += f"\n\n{utils.prettyLinks(links)}"

	print(f"Will try to message to u/{user} with: {replyText}")
	try:
		reply = message.reply(replyText)
		print(f"Successfully replied to message: {reply}")
	except Exception as e:
		# todo: maybe send it to the author of the comment?
		print(f"Error sending the message: {e}")

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
	comments = list(config.api.search_comments(author=user, filter=fields, q="|".join(words), size=1000))

	return recentComments+comments

def getUserPosts(user, fields=['id', 'title', 'selftext'], extraFields = []):
	return list(config.api.search_submissions(author=user, filter=fields+extraFields, size=500))

def getSaveKey(user, words):
	return f"{user}.{b64encode(str(words).encode('utf-8')).decode('utf-8')}"

@background
def saveCount(comment, user, words, count, countNR):
	key = getSaveKey(user, words)
	config.db.set(key, {"count": count, "countNR": countNR})
	config.db.dump()
	print(f"Saved count for: {key}")