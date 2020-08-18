import logging
import config
import utils
import re
import praw
import threading
from logging_config import tgLogger
from datetime import datetime
from datetime import timedelta
from durations import Duration
from utils import background
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from classes.queue import Queue
from praw.models import Comment

from prawcore import Forbidden
from prawcore import NotFound

def isTargetBlacklisted(user):
	return user.lower() in config.TARGET_USER_BLACKLIST

def isCallerBlacklisted(user):
	return user.lower() in config.CALLER_USER_BLACKLIST

def processUnreadItem(item):
	isComment = isinstance(item, Comment)
	logging.info(f"Processing unread message by u/{item.author}: {item.body}, comment={isComment}")

	try:
		result = processComment(item) if isComment else processMessage(item)
	except Exception as e:
		logging.info(f"Failed to process unread message: {e}")

# returns False if no match or (botname, username, words, withLinks)
def parseCommandText(body):
	text = utils.markdownToText(body)
	match = re.search(config.COMMAND_PATTERN, text, flags=re.IGNORECASE)

	if match and match.group(1):
		words = match.group(5)
		words = config.DEFAULT_TARGET_WORDS if (words is None) else words[1:-1].split(',')
		words = config.N_WORDS if "nword" in match.group(1) else words

		return (match.group(2), match.group(4), words, match.group(7)) 
	else:
		return False

def processComment(comment):
	if utils.is_processed(comment.id):
		logging.info(f"Skipping already processed comment: {comment}")
		return;

	result = parseCommandText(comment.body)
	if result:
		processSummoning(comment, *result)

def processSummoning(comment, bot, user, words, withLinks = False):
	caller = comment.author.name
	if isCallerBlacklisted(caller):
		logging.info(f"Skipping blacklisted caller user: u/{caller}")
		return

	state = config.redis
	inflight = f"inflight_{comment.id}"

	if state.get(inflight):
		logging.info(f"Skipping already inflight comment from processing: {comment.id}")
		return;

	logging.info(f"Processing summoning by u/{comment.author}: {comment.body}")

	if not user and not comment.parent().author:
		logging.info(f"Skipping a comment without target user and probably deleted parent comment: {comment.id}")
		return
	user = user or comment.parent().author.name

	state.set(inflight, 1)
	if user:
		if isTargetBlacklisted(user):
			if user == bot and bot == config.BOTNAME:
				try:
					comment.reply(config.COUNTER_REPLY_NO_SNITCHING_ON_ME)
					logging.info("Sent no snitching on me reply.")
				except Exception as e:
					logging.info(f"Couldn't send no snitching on me reply. Oh well. Error: {e}")

			logging.info(f"Skipping blacklisted target user: u/{user}")
			state.delete(inflight)
			return

		try:
			result = analyzeUser(user, words, comment, withLinks)
			banIfNeeded(caller, user, words, result)
			sendCounterComment(comment, user, words, *result)
		except Exception as e:
			print(f"Failed to finish processing summoning comment: {e}")

	state.delete(inflight)

def processMessage(message):
	caller = message.author.name
	if isCallerBlacklisted(caller):
		logging.info(f"Skipping blacklisted caller user: u/{caller}")
		return

	result = parseCommandText(message.body)
	if result:
		(bot, user, words, withLinks) = result
		if user:
			if isTargetBlacklisted(user):
				logging.info(f"Skipping blacklisted user {user}")
				return
			result = analyzeUser(user, words, withLinks = withLinks)
			banIfNeeded(caller, user, words, result)
			sendCounterMessage(user, words, *result, message=message)
		else:
			logging.info("Message didn't have a target body, skipping.")

def analyzeUser(user, words=config.N_WORDS, comment = None, withLinks = False):
	logging.info(f"Analyzing user u/{user} for word(s): {', '.join(words)}")

	isNwords = words == config.N_WORDS
	recentComments = []
	try:
		recentComments = list(config.reddit.redditor(user).comments.new())
	except Forbidden as e:
		logging.info(f"Unauthorized to fetch recent comments, user was probably suspended from Reddit: {e}")

	submissions = getUserPosts(user)
	comments = list(config.api.search_comments(author=user, filter=['body', 'id', 'permalink'], q="|".join(words), size=1000))

	logging.info(f"Found {len(comments)} comments for u/{user} from pushshift and {len(recentComments)} recent comments.")

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
	commentsWithoutLinks = []
	commentIds = []
	for c in (recentComments+comments):
		if c.id in processedComments:
			continue
		processedComments.append(c.id)

		count = countTextForWords(words, c.body) if(hasattr(c, 'body')) else 0
		totalMatches += count
		if count > 0:
			commentIds.append(c.id)
			if withLinks and hasattr(c, 'permalink'):
				links.append(c.permalink)
		if isNwords:
			totalNRMatches += countTextForWords(words[2:], c.body) if(hasattr(c, 'body')) else 0

	logging.info(f"Finished analyzing user u/{user}, results: {totalMatches}, {totalNRMatches}")
	
	links = list(map(lambda x: utils.linkify(x), links))

	return totalMatches, totalNRMatches, links, commentIds

def countTextForWords(words, text):
	pattern = r"({q})".format(q='|'.join(words))
	return len(re.findall(pattern, text.lower(), flags=re.IGNORECASE))

def sendCounterComment(comment, user, words, count, countNR, links = [], commentIds = []):
	saveCount(user, words, count, countNR, comment)

	replyText = utils.buildCounterReply(user, words, count, countNR);
	if commentIds or links:
		replyText += f"\n\nLinks:"
		if commentIds:
			replyText += f"\n\n0: [Pushshift]({utils.apiCommentsJsonLink(commentIds)})"
		if links:
			replyText += f"\n\n{utils.prettyLinks(links)}"

	logging.info(f"Will try to comment to reply with: {replyText}")
	try:
		reply = comment.reply(replyText)
		logging.info(f"Successfully replied with a comment: {utils.linkify(reply)}")
		utils.set_processed(comment.id)
	except Exception as e:
		logging.info(f"Couldn't send counter reply with a comment so will try to send a message instead: {e}")
		sendCounterMessage(user, words, count, countNR, links, commentIds, comment=comment)

def sendCounterMessage(user, words, count, countNR, links = [], commentIds = [], message = None, comment = None):
	if not (message or comment):
		raise ValueError("Can't send a message without message or comment")

	saveCount(user, words, count, countNR, comment, message)

	replyText = utils.buildCounterReply(user, words, count, countNR);
	if commentIds or links:
		replyText += f"\n\nLinks:"
		if commentIds:
			replyText += f"\n\n0: [Pushshift]({utils.apiCommentsJsonLink(commentIds)})"
		if links:
			replyText += f"\n\n{utils.prettyLinks(links)}"

	logging.info(f"Will try to message to u/{message.author.name} with: {replyText}")
	try:
		if message:
			reply = message.reply(replyText)
		elif comment:
			replyPrefix = f"{utils.linkify(comment.context)}\n\n" if hasattr(comment, 'context') else None
			if replyPrefix:
				replyText = replyPrefix + replyText
			reply = comment.author.message(config.BOTNAME, replyText)
			utils.set_processed(comment.id)
		logging.info(f"Successfully sent counter message")
	except Exception as e:
		logging.info(f"Error sending the message: {e}")

def processCommentWithCheck(comment):
	comment.refresh()
	alreadyReplied = False
	for c in comment.replies:
		if c.author == config.BOTNAME:
			logging.info(f"Already replied to comment {comment.id} with comment {utils.linkify(c)}")
			alreadyReplied = True
			break
	if not alreadyReplied:
		logging.info(f"Will process comment by '{comment.author}': {comment.body}, {utils.linkify(comment)}")
		processComment(comment)
		return True
	else:
		logging.info(f"Skipping already processed comment: {utils.linkify(comment)}" )
		return False

def processCommentById(id):
	return processCommentWithCheck(getCommentById(id))

def processPostComments(post=None, id=None, workers=10):
	if post and (post.locked or post.archived):
		logging.info("Post is locked or archived, skipping")
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

def getUserPosts(user, fields=['id', 'title', 'selftext', 'permalink']):
	return list(config.api.search_submissions(author=user, filter=fields, size=1000))

def banIfNeeded(caller, user, words, result):
	(count,countNR,links,cIds) = result
	if count > 1000:
			if caller == user:
				tgLogger.info(f"Auto banning user: https://reddit.com/u/{caller}, ({count}, {countNR})")
				with open("data/auto_bans.txt", "a+") as file:
					file.write(f"{caller.lower()}\n")

@background
def saveCount(user, words, count, countNR, comment = None, message = None):
	wordsTableEncoded = f"{b64encode(str(words).encode('utf-8')).decode('utf-8')}"
	stats = config.db.table(wordsTableEncoded)
	stats.insert({"user": user, "count": count, "countNR": countNR, "timestamp": utils.timestamp()})
	logging.info(f"Saved stats count for {user} and using words {words}")