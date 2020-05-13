#!env python
#

import argparse
import getpass
import github3
import json
import logging
import os
import re
import requests
import stashy
import stat

from furl import furl
from git import Repo
import git
from slugify import slugify

import migrate_config as config

import platform
if platform.system() == "Darwin":
	import caffeine

#
# The stashy library runs a command to populate the cookies (for an unknown reason).  However, in the symc
# bitbucket this causes the use to be logged out.  Therefore, intercept this specific call and return the
# cookies already present in the session.
#
class CustomSession(requests.Session):
	def __init__(self, ignore_url):
		super().__init__()
		self.ignore_url = ignore_url

	def head(self, url, **kwargs):
		if url == self.ignore_url:
			r = requests.Response()
			r.cookies = self.cookies
			return r

		return super().head(url, **kwargs)

class MirrorRepo:
	def __init__(self, location, sourceProjectName, sourceProjectSlug, sourceName, sourceUrl):
		self.location = location
		self.sourceProjectName = sourceProjectName
		self.sourceProjectSlug = sourceProjectSlug
		self.sourceName = sourceName
		self.sourceUrl = sourceUrl
		self.localRepo = None
		self.destinationName = None
		self.destinationRepository = None

	def __str__(self):
		return "{}/{}".format(self.sourceProjectSlug, self.sourceName)

class SourceRepoBase:
	def __init__(self):
		pass

	def ignore(self, projectSlug, repoName, repo=None):
		ignore = False
		if projectSlug in config.ignore["repos"]:
			if repoName in config.ignore["repos"][projectSlug]:
				ignore = True

		if projectSlug in config.ignore["patterns"]:
			for pattern in config.ignore["patterns"][projectSlug]:
				if re.search(pattern, repoName) is not None:
					ignore = True
					break

		if repo is not None and config.ignore['forkedReposInUser'] and 'origin' in repo:
			ignore = True

		if ignore:
			self.logger.info("Ignored repo {}/{}".format(projectSlug, repoName))

		return ignore

class SourceRepos(SourceRepoBase):
	def __init__(self):
		super(SourceRepos, self).__init__()
		self.logger = logging.getLogger(self.__class__.__name__)
		self.stashy = None
		self.session = None
		self.cachedRepos = {}

	def getAllRepos(self, project):
		if project in self.cachedRepos:
			return self.cachedRepos[project]

		repos = self.stashy.projects[project].repos.list()

		processedRepos = []
		for repo in repos:
			if self.ignore(project, repo['name'],repo):
				continue

			cloneUrls = list(filter(lambda x: x['name'] == "http", repo['links']['clone']))
			if len(cloneUrls) == 0:
				raise Exception("Cannot find clone URL for {}".format(repo['name']))

			splitUrl = furl(cloneUrls[0]['href'])
			splitUrl.username = config.source['username']
			splitUrl.password = config.source['apiKey']

			processedRepos.append({
				'name': repo['name'],
				'slug': repo['slug'],
				'url': splitUrl.tostr()
			})

		if config.source['repoSlugs'] is not None and project in config.source['repoSlugs']:
			# Only use repos in this list
			processedRepos = list(filter(lambda x: x['slug'] in config.source['repoSlugs'][project], processedRepos))

		self.logger.debug("*** {}".format(json.dumps(processedRepos)))
		self.cachedRepos[project] = processedRepos

		return processedRepos

	def getProjectName(self, project):
		prj = self.stashy.projects[project].get()

		return prj['name']

	def signin(self):
		url = "https://{}/".format(config.source['host'])

		if len(config.source['apiKey']) == 0:
			pw = os.environ.get('PW', None)
			if pw is None:
				pw = getpass.getpass('Password: ')

			session = CustomSession("{}rest/".format(url))
			session.post("{}/{}".format(url, '/j_atl_security_check'), verify=True, data={
				'j_username': config.source['username'],
				'j_password': pw,
				'_atl_remember_me': 'on',
				'submit': 'Log in'
			})

			client = stashy.client.Stash(url, session=session, verify=True)
		else:
			client = stashy.connect(url, config.source['username'], config.source['apiKey'], verify=True)
			session = client._client._session

		self.stashy = client
		self.session = session

	def enumerateRepos(self):
		mirrorRepos = []

		for projectSlug in config.source['projectSlugs']:
			baseDir = os.path.join(config.mirror['location'], projectSlug)
			os.makedirs(baseDir, exist_ok=True)

			projectName = self.getProjectName(projectSlug)
			repositories = self.getAllRepos(projectSlug)
			if len(repositories) == 0:
				self.logger.warn("No repositories found for project {}".format(projectSlug))
			else:
				for repo in repositories:
					r = MirrorRepo(
						os.path.join(config.mirror['location'], projectSlug, "{}.git".format(repo['slug'])),
						projectName,
						projectSlug,
						repo['slug'],
						repo['url'])

					mirrorRepos.append(r)
		if "userSlugs" in config.source:
			for userSlug in config.source['userSlugs']:
				baseDir = os.path.join(config.mirror['location'],userSlug)
				os.makedirs(baseDir, exist_ok=True)

				repositories = self.getAllRepos(userSlug)
				if len(repositories) == 0:
					self.logger.warn("No repositories found for user {}".format(userSlug))
				else:
					for repo in repositories:
						r = MirrorRepo(
							os.path.join(config.mirror['location'], userSlug, "{}.git".format(repo['slug'])),
							userSlug,
							userSlug,
							repo['slug'],
							repo['url'])

						mirrorRepos.append(r)

		self.mirrorRepos = mirrorRepos

	def updateRepo(self, repo):
		self.logger.info("Updating repo {}/{} at {}".format(repo.sourceProjectName, repo.sourceName, repo.location))
		repo.localRepo.remotes["origin"].set_url(repo.sourceUrl)
		exc = None
		for i in range(3):
			try:
				repo.localRepo.remotes["origin"].update(prune=True)
				return
			except git.exc.GitCommandError as e:
				exc = e

		raise exc

	def mirrorRepo(self, repo):
		self.logger.info("Mirroring repo from {}/{} to {}".format(repo.sourceProjectName, repo.sourceName, repo.location))
		exc = None
		for i in range(3):
			try:
				return Repo.clone_from(repo.sourceUrl, repo.location, multi_options=[ "--mirror", "-c credential.helper=" ])
			except git.exc.GitCommandError as e:
				exc = e

		raise exc

	def cloneRepos(self, updateExistingRepos):
		for repo in self.mirrorRepos:
			repoStat = None
			try:
				repoStat = os.stat(repo.location)
			except FileNotFoundError:
				pass

			if repoStat is None:
				repo.localRepo = self.mirrorRepo(repo)
			elif stat.S_ISDIR(repoStat.st_mode):
				repo.localRepo = Repo(repo.location)

				if updateExistingRepos:
					self.updateRepo(repo)
				else:
					self.logger.warning("Repo {} already exists but not updating existing repos".format(repo))
			else:
				raise Exception("Repo directory {} is not a directory".format(repo.location))

class LocalRepos(SourceRepoBase):
	def __init__(self):
		super(LocalRepos, self).__init__()
		self.logger = logging.getLogger(self.__class__.__name__)
		self.repos = None

	def enumerateRepos(self):
		repos = []
		for projectDir in [f for f in os.listdir(config.mirror['location']) if not f.startswith('.')]:
			for repoDir in [f for f in os.listdir(os.path.join(config.mirror['location'], projectDir)) if not f.startswith('.')]:
				if not self.ignore(projectDir, repoDir):
					repoName = repoDir
					if repoName.endswith(".git"):
						repoName = repoName[:-4]

					r = MirrorRepo(
						os.path.join(config.mirror['location'], projectDir, repoDir),
						None,
						projectDir,
						repoName,
						None)

					self.logger.debug("repoDir {} to {}".format(repoDir, repoName))
					r.localRepo = Repo(path=r.location)
					repos.append(r)

		self.repos = repos
		self.logger.info("Found {} repositories to migrate".format(len(self.repos)))

class DestinationRepos:
	def __init__(self, dryRun=False):
		self.logger = logging.getLogger(self.__class__.__name__)
		self.dryRun = dryRun
		self.repos = None
		self.gh = github3.enterprise_login(
			username=config.destination['username'],
			token=config.destination['apiKey'],
			url="https://{}".format(config.destination['host'])
		)
		self.org = None
		self.teams = {}
		self.remoteRepos = {}

	def signin(self):
		if self.dryRun:
			return

		try:
			if len(config.source['projectSlugs']) != 0:
				for org in self.gh.organizations():
					self.logger.debug(
						"User is a member of organisation {}".format(org.login, config.destination['orgName']))
					if org.login == config.destination['orgName']:
						self.org = org

				if self.org is None:
					raise Exception("Organisation {} not found".format(config.destination['orgName']))

				for team in self.org.teams():
					self.logger.debug("Team: {}".format(team.name))
					self.teams[team.name] = team

				if config.destination['teamOwner'] not in self.teams:
					raise Exception(
						"Team owner {} is not part of the {} organisation".format(config.destination['teamOwner'],
																				  self.org.login))

				for r in self.org.repositories():
					self.logger.debug("* Repository {}".format(r.name))
					self.remoteRepos[r.name] = r

			if "userSlugs" in config.source and len(config.source['userSlugs']) != 0:
				for r in self.gh.repositories():
					self.logger.debug("* Repository {}".format(r.name))
					self.remoteRepos[r.name] = r

			else:
				raise Exception("Atleast ProjectSlug or UserSlug must be provided.")

		except github3.exceptions.ConnectionError:
			raise Exception("Failed to connect to Github host {}".format(config.destination['host']))

	def setRepos(self, repos):
		self.repos = repos

		duplicateCheck = {}
		for repo in self.repos:
			if '~' == repo.sourceProjectSlug[0]:
				repoName = repo.sourceName
			else:
				repoName = self.makeRepoName(repo)

			if repoName in duplicateCheck:
				raise Exception("Repository {} wants to be named {} but a different repository maps to this name already".format(repo.sourceName, repoName))

			repo.destinationName = repoName

	def makeRepoName(self, repo):
		r = [ config.destination['teamPrefix'] ]

		projectPrefix = repo.sourceProjectSlug
		if repo.sourceProjectSlug in config.destination['projectSlugMappings']:
			projectPrefix = config.destination['projectSlugMappings'][repo.sourceProjectSlug]

		# Has this repo been remapped to a different name?
		if repo.sourceProjectSlug in config.destination["repoNameMapping"] and repo.sourceName in config.destination["repoNameMapping"][repo.sourceProjectSlug]:
			r.append(config.destination["repoNameMapping"][repo.sourceProjectSlug][repo.sourceName])
		else:
			if config.destination["useProjectPrefix"] and not repo.sourceName.startswith(projectPrefix):
				r.append(projectPrefix)

			r.append(repo.sourceName)

		return str.join("-", r)

	def getTeam(self, teamName):
		if teamName not in self.teams:
			raise Exception("Team {} not found".format(teamName))
		return self.teams[teamName]

	def createRemoteRepos(self):
		for repo in self.repos:
			self.logger.debug("Repository {}:".format(repo.destinationName))
			setPermissions = True

			if repo.destinationName not in self.remoteRepos:
				self.logger.info("Creating new repository {}".format(repo.destinationName))
				if not self.dryRun:
					if '~' == repo.sourceProjectSlug[0]:
						repo.destinationRepository = self.gh.create_repository(
							repo.destinationName,
							has_wiki=False,
							private=True
						)
					else:
						repo.destinationRepository = self.org.create_repository(
							repo.destinationName,
							has_wiki=False,
							private=True,
							team_id=self.getTeam(config.destination['teamOwner']).id
						)

				self.logger.debug("* Repo created")
			else:
				self.logger.debug("* Repo already exists")
				repo.destinationRepository = self.remoteRepos[repo.destinationName]

				if config.destination["skipPermissionsIfRepoExists"]:
					setPermissions = False

			if '~' == repo.sourceProjectSlug[0]:
				self.logger.info("Skip adding any Team permissions for personal repo {}".format(repo.destinationName))
				continue

			if setPermissions:
				# Set permissions
				for perm in config.destination['repoAccess']:
					teamName = config.destination['repoAccess'][perm]
					self.logger.info("Team {} wants permission {} on {}".format(teamName, perm, repo.destinationName))

					if not self.dryRun:
						team = self.getTeam(teamName)
						repoPath = "{}/{}".format(self.org.login, repo.destinationName)

						if not team.has_repository(repoPath):
							self.logger.info("Adding team {} with permission {} to {}".format(team.name, perm, repoPath))
							team.add_repository(repoPath, perm)

	def addRemoteToRepos(self):
		for repo in self.repos:
			url = furl(repo.destinationRepository.clone_url)
			url.username = config.destination['username']
			url.password = config.destination['apiKey']

			if 'target' not in repo.localRepo.remotes:
				self.logger.debug("Create remote of target to {}".format(repo.destinationRepository.clone_url))
				if not self.dryRun:
					repo.localRepo.create_remote('target', url.tostr())
			else:
				if not self.dryRun:
					repo.localRepo.remotes["target"].set_url(url.tostr())

	def pushRepo(self, repo):
		if not self.dryRun:
			self.logger.info("Pushing repository {}".format(repo.destinationName))
			repo.localRepo.remote('target').push("--mirror")

	def pushRepos(self):
		for repo in self.repos:
			self.pushRepo(repo)

if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--dry-run",
		help="Do not push changes or create repositories.",
		action='store_true'
	)
	parser.add_argument(
		"--mode",
		help="Mode",
		choices=['clone', 'clone_update', 'push'],
		required=True
	)
	parser.add_argument(
		"--loglevel",
		help="Log level",
		choices=["debug", "info", "warning", "error"],
		default="info"
	)

	args = parser.parse_args()

	dryRun = args.dry_run

	logLevel = getattr(logging, args.loglevel.upper(), None)
	if not isinstance(logLevel, int):
		raise ValueError('Invalid log level: {}'.format(args.loglevel))
	logging.basicConfig(
		level=logLevel,
		format='%(asctime)s %(name)s %(levelname)s:%(message)s',
		datefmt='%Y-%m-%dT%H:%M:%S'
	)
	logging.getLogger('github3').setLevel(logging.WARNING)

	logger = logging.getLogger("main")

	if args.mode in [ "clone", "clone_update" ]:
		logger.info("Source is https://{}@{}".format(config.source['username'], config.source['host']))

		source = SourceRepos()
		source.signin()
		source.enumerateRepos()

		source.cloneRepos(args.mode == "clone_update")
	else:
		source = LocalRepos()
		source.enumerateRepos()

		destination = DestinationRepos(dryRun=args.dry_run)
		destination.signin()

		destination.setRepos(source.repos)
		destination.createRemoteRepos()
		destination.addRemoteToRepos()
		destination.pushRepos()
