import os
from dotenv import load_dotenv, find_dotenv
from psaw import PushshiftAPI
import praw

def env(key, fallback):
	return os.getenv(key, fallback)

load_dotenv(find_dotenv())

BOTNAME = 'wordscounterbot'
SUBREDDIT = 'all'
USER_AGENT = 'u/wordscounterbot. Contact me at /u/alashow or me@alashov.com'

REDIS_HOST=env("REDIS_HOST", 'localhost')
REDIS_PORT=env("REDIS_PORT", 6379)
REDIS_PASSWORD=env("REDIS_PASSWORD", "")

N_WORDS = ["nigga", "nigger"]
DEFAULT_TARGET_WORDS=N_WORDS
TARGET_USER_BLACKLIST=["AutoModerator"]
CENSOR_WORDS_MAP = ('nigga', 'n-word'), ('nigger', 'n-word-R')
COUNTER_REPLY_TEMPLATE="Hey, I've searched u/{user}'s comments and found **{count}** matches for word(s) '{words}'"

reddit = praw.Reddit(BOTNAME, user_agent=USER_AGENT)
api = PushshiftAPI(reddit)
sub = reddit.subreddit(SUBREDDIT)