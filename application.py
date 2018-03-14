from flask import Flask, request, render_template
from operator import attrgetter
from threading import Thread

import datetime
import json
import logging
import logging.handlers as log_handler
import requests

app = Flask(__name__)

"""CLIENT_ID and CLIENT_SECRET would better to save as environment variable"""
CLIENT_ID = "843cd42c1ce079f3f111"
CLIENT_SECRET = "f61274309f276507c96190963d412d086781b2e8"

HEADERS = {'Accept':'application/vnd.github.v3+json'}
URL = "https://api.github.com/search/repositories"

"""Logging to a file named as application.log"""
app_logger = logging.getLogger("github_task")
app_logger.setLevel(logging.WARNING)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

"""Rotates the application.log every day. Supports up to 7 backups"""
logger_file_handler = log_handler.TimedRotatingFileHandler('application.log', when='D', interval=1, backupCount=7)
logger_file_handler.setLevel(logging.WARNING)
logger_file_handler.setFormatter(formatter)

app_logger.addHandler(logger_file_handler)

"""Since requests library does not support non-blocking requests,
a multithreaded mechanism is added for making api calls for detailed commit info
"""
class RequestThread(Thread):
	def __init__(self, rname, rurl, rparams, **kwargs):
		Thread.__init__(self, name=rname)
		self.url = rurl[ : rurl.find("{")]
		self.params = rparams
		self.name = rname
		self.respository_name = kwargs.get("repo_name", "")
		self.created_at = kwargs.get("created_at", "")
		self.owner_login = kwargs.get("owner_login", "")
		self.owner_url = kwargs.get("owner_url", "")
		self.owner_avatar_url = kwargs.get("owner_avatar_url", "")
		self.sha = ""
		self.commit_message = ""
		self.commit_author_name = ""
		self.repo_info_dict = None

	def run(self):
		"""Gets sha, message and author name about the latest commit"""
		with requests.Session() as s:
			res = s.get(url=self.url, params=self.params, headers=HEADERS)
			if res.status_code == 200:
				res = res.json()
				if len(res) > 0:
					self.sha = res[0]["sha"]
					self.commit_message = res[0]["commit"]["message"]
					self.commit_author_name = res[0]['commit']['author']['name']
			else:
				app_logger.warning(res.text)

	def __str__():
		return "Name-{0} with commit_url: {1}".format(self.name, self.url)

	@property
	def get_repo_info(self):
		if not self.repo_info_dict:
			self.repo_info_dict = {
				'id' : self.name,
				"repo_name" : self.respository_name,
				"created_at" : self.created_at,
				"owner_login" : self.owner_login,
				"owner_url" : self.owner_url,
				"owner_avatar_url" : self.owner_avatar_url,
				"sha" : self.sha,
				"commit_message" : self.commit_message,
				"commit_author_name" : self.commit_author_name,
				}
		return self.repo_info_dict

@app.route('/navigator', methods=['GET'])
def navigator():
	"""Gets the latest (by creation date) 5 repositories with related information"""
	search_term = request.args.get("search_term", '')
	session = requests.Session()
	param_dict = {
		'q' : '{0} in:name'.format(search_term),
		'page' : '1',
		'client_id' : CLIENT_ID,
		'client_secret' : CLIENT_SECRET,
		}
	
	response = session.get(url=URL, params=param_dict, headers=HEADERS)
	total_count = None
	if response.status_code == 200:
		response_json = response.json()
		total_count = response_json['total_count']
		if total_count:
			newest_repos = sorted(response_json['items'], key=lambda x:datetime.datetime.strptime(x['created_at'][:19], '%Y-%m-%dT%H:%M:%S'), reverse=True)[:5]
			thread_list = []
			thread_id = 1
			for repo_info in newest_repos:
				repo_dict = {}
				repo_dict["repo_name"] = repo_info["name"]
				repo_dict["created_at"] = repo_info["created_at"].replace("T", " ").replace("Z", "")
				repo_dict["owner_login"] = repo_info["owner"]["login"]
				repo_dict["owner_url"] = repo_info["owner"]["url"]
				repo_dict["owner_avatar_url"] = repo_info["owner"]["avatar_url"]
				current_thread = RequestThread(thread_id, repo_info["commits_url"], {'client_id' : CLIENT_ID, 'client_secret' : CLIENT_SECRET}, **repo_dict)
				current_thread.start()
				thread_list.append(current_thread)
				thread_id += 1
		
			for t in thread_list:
				t.join()
	else:
		app_logger.warning(response.text)

	session.close()
	try:
		repo_info_list = map(lambda x:x.get_repo_info, thread_list)
	except Exception as e:
		repo_info_list = []
		total_count = None
		app_logger.error(e)

	return render_template("template.html", total_count=total_count, search_term=search_term, repo_info_list=repo_info_list, message="No result is found")

if __name__ == "__main__":
	app.run()