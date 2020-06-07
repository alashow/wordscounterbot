import config
import logging
from redis import StrictRedis
from functools import reduce
from bs4 import BeautifulSoup
from markdown import markdown

def buildCounterReplyComment(user, count, words):
	words = list(map(lambda w: censor(w), words))
	words = words[0] if len(words) == 1 else ", ".join(words)

	return config.COUNTER_REPLY_TEMPLATE.format(user=user, count=count, words=words)

def redis():
	return StrictRedis(host=config.REDIS_HOST, port=config.REDIS_PORT, password=config.REDIS_PASSWORD, db=0)

def censor(s):
	return reduce(lambda a, kv: a.replace(*kv), config.CENSOR_WORDS_MAP, s)

def markdownToText(text):
	return ''.join(BeautifulSoup(markdown(text), "html.parser").findAll(text=True))

def linkify(c):
	return 'https://reddit.com/'+c.permalink