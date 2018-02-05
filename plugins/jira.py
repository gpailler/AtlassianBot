# coding: utf-8

import inspect
import re
import json
import logging
from itertools import filterfalse

import arrow
from jira import JIRA
from jira.exceptions import JIRAError
from lazy import lazy

from slackbot.bot import Bot, listen_to, respond_to

from . import settings
from utils.messages_cache import MessagesCache
from utils.imageproxy import converturl_proxyurl
from utils.notifier_bot import NotifierBot, NotifierJob

logger = logging.getLogger(__name__)

MAX_NOTIFIERS_WORKERS = 2


def get_Jira_instance(server):
    auth = None
    if 'username' in server and 'password' in server:
        auth = (server['username'], server['password'])

    return JIRA(
        options={
            'server': server['host'],
            'verify': settings.servers.verify_ssl},
        basic_auth=auth,
        get_server_info=False,
        max_retries=1
    )


class JiraBot(object):
    def __init__(self, cache, jira_server, imageproxy_server, prefixes):
        self.__cache = cache
        self.__jira_server = jira_server
        self.__imageproxy_server = imageproxy_server
        self.__prefixes = prefixes
        self.__jira_regex = re.compile(self.get_pattern(), re.IGNORECASE)

    @lazy
    def __jira(self):
        return get_Jira_instance(self.__jira_server)

    def get_pattern(self, prefixes=None):
        if prefixes is None:
            prefixes = self.__prefixes

        jira_prefixes = '|'.join(prefixes)
        return r'(?:^|\s|[\W]+)(?<!CLEAN\s)((?:{})-[\d]+)(?:$|\s|[\W]+)'\
            .format(jira_prefixes)

    def get_prefixes(self):
        return self.__prefixes

    def get_issue_status(self, key):
        try:
            issue = self.__jira.issue(key, fields='status')
            return issue.fields.status.name
        except JIRAError:
            return None

    def close(self, key, user):
        issue = self.__jira.issue(key, fields='subtasks,status')
        comment = 'Closed by AtlassianBot (Original user: {})'.format(user)
        for subtask in issue.fields.subtasks:
            if str(subtask.fields.status) != 'Closed':
                self.__jira.transition_issue(
                    subtask,
                    'Closed',
                    comment=comment,
                    assignee={'name': user}
                )

        if str(issue.fields.status) != 'Closed':
            self.__jira.transition_issue(
                issue,
                'Closed',
                comment=comment,
                assignee={'name': user}
            )

    def display_issues(self, message):
        attachments = []

        issues = self.__jira_regex.findall(message.body['text'])

        def filter_predicate(x):
            return self.__cache.IsInCache(self.__get_cachekey(x, message))

        for issue in filterfalse(filter_predicate, issues):
            self.__cache.AddToCache(self.__get_cachekey(issue, message))
            issue_message = self.get_issue_message(issue)
            if issue_message is None:
                issue_message = self.__get_issuenotfound_message(issue)

            attachments.append(issue_message)

        if attachments:
            message.send_webapi('', json.dumps(attachments))

    def get_issue_message(self, key):
        try:
            issue = self.__jira.issue(key, fields='summary,issuetype')
            icon = converturl_proxyurl(
                                    self.__imageproxy_server['host'],
                                    issue.fields.issuetype.iconUrl)
            summary = issue.fields.summary.encode('utf8')
            return {
                'fallback': '{key} - {summary}\n{url}'.format(
                    key=issue.key,
                    summary=summary.decode(),
                    url=issue.permalink()
                    ),
                'author_name': issue.key,
                'author_link': issue.permalink(),
                'author_icon': icon,
                'text': summary.decode(),
                'color': '#59afe1'
            }
        except JIRAError as ex:
            return self.__get_error_message(ex)

    def __get_issuenotfound_message(self, key):
        return {
            'fallback': 'Issue {key} not found'.format(key=key),
            'author_name': key,
            'text': ':exclamation: Issue not found',
            'color': 'warning'
        }

    def __get_error_message(self, exception):
        if (exception.status_code == 401):
            return {
                'fallback': 'Jira authentication error',
                'text': ':exclamation: Jira authentication error',
                'color': 'danger'
            }

    def __get_cachekey(self, issue, message):
        return issue + message.body['channel']


class JiraNotifierBot(NotifierBot):
    def __init__(self,
                 jira_server,
                 imageproxy_server,
                 config,
                 slackclient=None):
        super().__init__(slackclient)

        self.__jira_server = jira_server
        self.__imageproxy_server = imageproxy_server
        self._jobs = list(self.submit_jobs(config))

    def submit_jobs(self, config):
        for notifier_settings in config['notifiers']:
            logger.info('registered JiraNotifierBot for query \'%s\' '
                        'on channel \'#%s\'',
                        notifier_settings['query'],
                        notifier_settings['channel'])

            job = JiraNotifierJob(
                                  self.__jira,
                                  self.__imageproxy_server,
                                  notifier_settings,
                                  config['polling_interval'])

            self.submit(job)
            yield job

    @lazy
    def __jira(self):
        return get_Jira_instance(self.__jira_server)


class JiraNotifierJob(NotifierJob):
    def __init__(self, jira, imageproxy, config, polling_interval):
        super().__init__(config['channel'], polling_interval)
        self.__jira = jira
        self.__imageproxy = imageproxy
        self.__config = config

    def init(self):
        # First query to retrieve last matching task
        query = '{} AND status = Closed ORDER BY updated DESC'\
            .format(self.__config['query'])

        results = self.__jira.search_issues(query, maxResults=1)

        if len(results) == 0:
            logger.error('No initial issue found')
            return

        self.__last_result = results[0]

    def run(self):
        # Convert last issue update date
        # to a compatible timestamp for Jira
        date = arrow.get(self.__last_result.fields.updated)

        last_update = (date.timestamp + 1) * 1000
        query = '{} AND status CHANGED TO Closed DURING({}, NOW()) '\
                'ORDER BY updated DESC'\
            .format(self.__config['query'], last_update)

        fields = 'summary,customfield_10012,updated,issuetype,assignee'
        results = self.__jira.search_issues(
                        query,
                        fields=fields,
                        expand='changelog')

        if len(results) > 0:
            self.__last_result = results[0]
            attachments = []
            for issue in results[::-1]:
                summary = issue.fields.summary.encode('utf8')
                icon = converturl_proxyurl(
                                self.__imageproxy['host'],
                                issue.fields.issuetype.iconUrl)

                sps = self.__get_storypoints(issue)
                sps = self.__formatvalue(sps)

                author = self.__get_author(issue)
                author = self.__formatvalue(author)

                status = self.__get_status(issue)
                status = self.__formatvalue(status)

                attachments.append({
                    'fallback': '{key} - {summary}\n{url}'.format(
                        key=issue.key,
                        summary=summary.decode(),
                        url=issue.permalink()
                        ),
                    'author_name': issue.key,
                    'author_link': issue.permalink(),
                    'author_icon': icon,
                    'text': summary.decode(),
                    'color': '#14892c',
                    'mrkdwn_in': ['fields'],
                    'fields': [
                        {
                            'title': '{} by'.format(status),
                            'value': author,
                            'short': True
                        },
                        {
                            'title': 'Story points',
                            'value': sps,
                            'short': True
                        }
                    ],

                })
            self.send_message(attachments)

    def __get_storypoints(self, issue):
        if hasattr(issue.fields, 'customfield_10012') and \
                issue.fields.customfield_10012 is not None:
            return issue.fields.customfield_10012

    def __get_author(self, issue):
        if len(issue.changelog.histories) > 0:
            event = issue.changelog.histories[-1]
            # Search in history in we have a transition to Closed
            # with a change of the assignee
            # => it's probably a transition done by the bot
            res = next((x for x in event.items if x.field == 'assignee'), None)
            if res is not None:
                author = res.to
            else:
                author = issue.fields.assignee.name

            return '<@{}>'.format(author)

    def __get_status(self, issue):
        if len(issue.changelog.histories) > 0:
            event = issue.changelog.histories[-1]
            for item in event.items:
                if item.field == 'status':
                    return item.toString

    def __formatvalue(self, value):
        return value if value else 'N/A'

    def __get_slackclient(self):
        stack = inspect.stack()
        for frame in [f[0] for f in stack]:
            if 'self' in frame.f_locals:
                instance = frame.f_locals['self']
                if isinstance(instance, Bot):
                    return instance._client

    def __get_channel(self, channelname):
        for id, channel in list(self.slackclient.channels.items()):
            if channel.get('name', None) == channelname:
                return id


if (settings.plugins.jiranotifier.enabled):
    JiraNotifierBot(
                    settings.servers.jira,
                    settings.servers.imageproxy,
                    settings.plugins.jiranotifier)

instance = JiraBot(
                   MessagesCache(),
                   settings.servers.jira,
                   settings.servers.imageproxy,
                   settings.plugins.jirabot.prefixes)


if (settings.plugins.jirabot.enabled):
    @listen_to(instance.get_pattern(), re.IGNORECASE)
    @respond_to(instance.get_pattern(), re.IGNORECASE)
    def jirabot(message, _):
        instance.display_issues(message)
