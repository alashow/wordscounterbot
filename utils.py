import config
import logging
from datetime import timedelta
from redis import StrictRedis
from functools import reduce
from bs4 import BeautifulSoup
from markdown import markdown
import threading
import pytz
from datetime import datetime

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

# https://dev.to/astagi/rate-limiting-using-python-and-redis-58gk
def rateLimit(key: str, limit: int, period: timedelta):
	r = redis()
	period_in_seconds = int(period.total_seconds())
	t = r.time()[0]
	separation = round(period_in_seconds / limit)
	r.setnx(key, 0)
	try:
		with r.lock('lock:' + key, blocking_timeout=5) as lock:
			tat = max(int(r.get(key)), t)
			if tat - t <= period_in_seconds - separation:
				new_tat = max(tat, t) + separation
				r.set(key, new_tat)
				return False
			return True
	except LockError:
		return True

def background(f):
    def wrapper(*a, **kw):
        threading.Thread(target=f, args=a, kwargs=kw).start()
    return wrapper

def datetime_force_utc(date_time):
	return pytz.utc.localize(date_time)

def datetime_as_utc(date_time):
	return date_time.astimezone(pytz.utc)

def datetime_from_timestamp(timestamp):
	return datetime_force_utc(datetime.utcfromtimestamp(timestamp))

def datetime_now():
	return datetime_force_utc(datetime.utcnow().replace(microsecond=0))

def datetime_from_timestamp(timestamp):
	return datetime_force_utc(datetime.utcfromtimestamp(timestamp))


def get_datetime_string(date_time, convert_utc=True, format_string="%Y-%m-%d %H:%M:%S"):
	if date_time is None:
		return ""
	if convert_utc:
		date_time = datetime_as_utc(date_time)
	return date_time.strftime(format_string)

def parse_datetime_string(date_time_string, force_utc=True, format_string="%Y-%m-%d %H:%M:%S"):
	if date_time_string is None or date_time_string == "None" or date_time_string == "":
		return None
	date_time = datetime.strptime(date_time_string, format_string)
	if force_utc:
		date_time = datetime_force_utc(date_time)
	return date_time

def get_last_seen(keyword):
	return datetime_from_timestamp(config.state.get(f"last_seen_{keyword}") or 0)

def set_last_seen(keyword, seen):
	config.state.set(f"last_seen_{keyword}", seen)