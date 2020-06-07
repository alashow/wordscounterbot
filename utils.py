import config
import logging
from redis import StrictRedis
from functools import reduce
from bs4 import BeautifulSoup
from markdown import markdown

def buildCounterReplyComment(user, words, count, countNR):
	isNwords = words == config.N_WORDS
	words = list(map(lambda w: censor(w), words))
	words = words[0] if len(words) == 1 else ", ".join(words)

	if isNwords:
		if count == 0 and countNR == 0:
			return config.COUNTER_REPLY_TEMPLATE_NWORD_NONE.format(user=user)
		else:
			return config.COUNTER_REPLY_TEMPLATE_NWORD.format(user=user, count=count, countNR=countNR)
	else:
		return config.COUNTER_REPLY_TEMPLATE.format(user=user, count=count, words=words)

def redis():
	return StrictRedis(host=config.REDIS_HOST, port=config.REDIS_PORT, password=config.REDIS_PASSWORD, db=0)

def censor(s):
	return reduce(lambda a, kv: a.replace(*kv), config.CENSOR_WORDS_MAP, s)

def markdownToText(text):
	return ''.join(BeautifulSoup(markdown(text), "html.parser").findAll(text=True))

def linkify(c):
	return 'https://reddit.com'+c.permalink