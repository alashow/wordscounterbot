import config
import re
import actions

for comment in config.sub.stream.comments(skip_existing=True):
	actions.processGlobalComment(comment)