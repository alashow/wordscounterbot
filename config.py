import os
from dotenv import load_dotenv, find_dotenv
from psaw import PushshiftAPI
import praw
import pickledb

def env(key, fallback):
	return os.getenv(key, fallback)

load_dotenv(find_dotenv())

BOTNAME = 'wordscounterbot'
SUBREDDIT = 'all'
USER_AGENT = 'u/wordscounterbot. Contact me at /u/alashow or me@alashov.com'

REDIS_HOST=env("REDIS_HOST", 'localhost')
REDIS_PORT=env("REDIS_PORT", 6379)
REDIS_PASSWORD=env("REDIS_PASSWORD", "")

N_WORDS = ["nigga", "niggas", "nigger", "niggers"]
DEFAULT_TARGET_WORDS=N_WORDS
CENSOR_WORDS_MAP = ('nigga', 'n-word'), ('nigger', 'n-word-R')
COUNTER_REPLY_TEMPLATE="Hey, I've searched u/{user}'s history and found **{count}** matches for word(s): {words}"
COUNTER_REPLY_TEMPLATE_NWORD="""Thank you for the request, comrade.

I have looked through u/{user}'s posting history and found {count} N-words, of which {countNR} were hard-Rs."""
COUNTER_REPLY_TEMPLATE_NWORD_NONE= """Thank you for the request, comrade.

u/{user} has not said the N-word yet."""

TARGET_USER_BLACKLIST=open('data/banned_redditors.txt').read().split('\n')

COMMAND_PATTERN = r"(u\/({bot}|nwordcountbot)) ?(u\/[a-zA-Z0-9-_]{{1,100}})? ?(\'(.*){{1,100}}\')?".format(bot=BOTNAME)
COMMAND_PATTERN = r"(\/?u\/({bot}|nwordcountbot)) ?(\/?u\/([a-zA-Z0-9-_]{{1,100}}))? ?(\'((.*){{1,100}})\')?".format(bot=BOTNAME)

reddit = praw.Reddit(BOTNAME, user_agent=USER_AGENT)
sub = reddit.subreddit(SUBREDDIT)
api = PushshiftAPI()
apiReddit = PushshiftAPI(reddit)

db = pickledb.load('data/stats.db', False)
state = pickledb.load('data/app.db', True)