import utils

import config
import utils
from classes.queue import Queue
from datetime import timedelta
import logging as log
import requests
import traceback

class RedditKeywordWatcher:
	def __init__(self, keyword):
		self.keyword = keyword
		self.processed_comments = Queue(100)
		self.consecutive_timeouts = 0
		self.timeout_warn_threshold = 1
		self.pushshift_lag = 0
		self.pushshift_lag_checked = None	

	def get(self):
		last_seen = utils.get_last_seen(self.keyword)
		log.debug(f"Fetching comments for keyword: {self.keyword} : {last_seen}")
		url = f"https://api.pushshift.io/reddit/comment/search?q={self.keyword}&limit=100&sort=desc&fields=created_utc,id"
		lag_url = "https://api.pushshift.io/reddit/comment/search?limit=1&sort=desc"
		try:
			json = requests.get(url, headers={'User-Agent': config.USER_AGENT}, timeout=10)
			if json.status_code != 200:
				log.warning(f"Could not parse data for search term: {self.keyword} status: {str(json.status_code)}")
				return []
			comments = json.json()['data']

			if self.pushshift_lag_checked is None or \
					utils.datetime_now() - timedelta(minutes=10) > self.pushshift_lag_checked:
				log.debug("Updating pushshift comment lag")
				json = requests.get(lag_url, headers={'User-Agent': config.USER_AGENT}, timeout=10)
				if json.status_code == 200:
					comment_created = utils.datetime_from_timestamp(json.json()['data'][0]['created_utc'])
					self.pushshift_lag = round((utils.datetime_now() - comment_created).seconds / 60, 0)
					self.pushshift_lag_checked = utils.datetime_now()

			if self.timeout_warn_threshold > 1:
				log.warning(f"Recovered from timeouts after {self.consecutive_timeouts} attempts")

			self.consecutive_timeouts = 0
			self.timeout_warn_threshold = 1

		except requests.exceptions.ReadTimeout:
			self.consecutive_timeouts += 1
			if self.consecutive_timeouts >= pow(self.timeout_warn_threshold, 2) * 5:
				log.warning(f"{self.consecutive_timeouts} consecutive timeouts for search term: {self.keyword}")
				self.timeout_warn_threshold += 1
			return []

		except Exception as err:
			log.warning(f"Could not parse data for search term: {self.keyword}")
			log.warning(traceback.format_exc())
			return []

		if not len(comments):
			log.warning(f"No comments found for search term: {self.keyword}")
			return []

		result_comments = []
		for comment in comments:
			date_time = utils.datetime_from_timestamp(comment['created_utc'])
			if last_seen > date_time:
				break

			if not self.processed_comments.contains(comment['id']):
				result_comments.append(comment)

		return result_comments

	def set_processed(self, comment_id):
		self.processed_comments.put(comment_id)