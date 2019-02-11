# coding: utf-8

import re
import json
import os
import fnmatch
from datetime import datetime, timedelta
from shutil import rmtree

from slackbot.bot import respond_to

from . import jira
from . import crucible
from . import bamboo
from . import stash
from . import settings

from utils.slackbot_utils import send_message

class CleanBot(object):
    PENDING_ACTIONS_VALIDITY = 30  # seconds
    __pending_actions = {}

    def __init__(self, settings, jira, bamboo, crucible, stash):
        self.__settings = settings[0]
        self.__jira = jira
        self.__bamboo = bamboo
        self.__crucible = crucible
        self.__stash = stash

    def get_pattern(self):
        jira_prefixes = '|'.join(self.__jira.get_prefixes())
        clean_pattern = r'CLEAN ((?:{})-[\d]+)'.format(jira_prefixes)
        return clean_pattern

    def generate_clean_tasks(self, message, key):
        key = key.upper()
        send_message(message, 'Yes my lord. I\'m looking for tasks...')
        self.__pending_actions.pop(message._get_user_id(), None)

        username = self._get_username(message)

        results = [
            self.__search_jira(key, username),
            self.__search_crucible(key),
            self.__search_git(key),
            self.__search_bamboo(key),
            self.__search_folders(key),
        ]

        messages = [y for x in results for y in x.messages]
        has_error = False
        for result in results:
            has_error |= result.has_error

        send_message(message, '', attachments=json.dumps(messages))
        if has_error:
            send_message(message, 'There are errors. Clean cannot be performed')
        else:
            actions = [y for x in results for y in x.actions]
            if len(actions) > 0:
                send_message(message, 'Send \'CLEAN YES\' to validate these changes')

                self.__pending_actions[message._get_user_id()] = {
                    'date': datetime.utcnow(),
                    'key': key,
                    'actions': actions
                }
            else:
                send_message(message, 'Nothing to clean')

    def execute_clean_tasks(self, message):
        allowed = False
        for user in self.__settings['allowedusers']:
            userid = message._client.find_user_by_name(user)
            if message.body['user'] == userid:
                allowed = True
                break

        if allowed is False:
            send_message(message, 'You\'re not authorized for this action')
            return

        result = self.__pending_actions.get(message._get_user_id(), None)
        if result:
            delta = timedelta(seconds=self.PENDING_ACTIONS_VALIDITY)
            if result['date'] + delta < datetime.utcnow():
                send_message(message,
                    ('Pending action for {} is not valid anymore.'
                     'You have {} seconds to validate the action.')
                    .format(result['key'], self.PENDING_ACTIONS_VALIDITY))
            else:
                send_message(message, 'Yes my lord. I\'m on it.')
                for action in result['actions']:
                    action()

                send_message(message, 'I\'m done!')
        else:
            send_message(message, 'No pending action found')

    def __search_jira(self, key, username):
        result = SearchResult('JIRA')
        status = self.__jira.get_issue_status(key)
        if status is None:
            result.add_error_message('Issue {} not found.'.format(key))
        else:
            issue = self.__jira.get_issue_message(key)
            result.add_message_formatted(issue)

            if status == 'Closed':
                result.add_message('{} already closed'.format(key), None)
            else:
                result.add_message(
                    '{} and all subtasks will be closed.'
                    .format(key)
                )

                result.add_action(
                    lambda k=key, u=username: self.__close_jira(k, u)
                )

        return result

    def __close_jira(self, key, user):
        self.__jira.close(key, user)

    def __search_crucible(self, key):
        result = SearchResult('CRUCIBLE')
        reviews = self.__crucible.get_reviews_from_jira(key)
        if len(reviews) == 0:
            result.add_message('No linked reviews found.', None)
        else:
            for review in reviews:
                if review['state'] != 'Closed' and review['state'] != 'Dead':
                    result.add_error_message(
                                    'Review {} is not closed.'
                                    .format(review['permaId']['id']))

            if not result.has_error:
                result.add_message('All linked reviews are closed.', None)

        return result

    def __search_git(self, key):
        result = SearchResult('STASH')
        branches = self.__stash.get_stash_branches(
                         self.__settings['stash']['repos'],
                         self.__settings['stash']['project'],
                         key)
        if len(branches) == 0:
            result.add_message('No linked Git branch to remove.', None)
        else:
            for repo, branchkey, branchname, changeset in branches:
                if self.__stash.branch_merged(
                        self.__settings['stash']['project'],
                        self.__settings['stash']['basebranches'],
                        repo,
                        branchkey):
                    result.add_message(
                                'Git branch {} {} will be removed.'
                                .format(repo, branchname))
                    result.add_action(
                        lambda r=repo, b=branchkey, c=changeset:
                            self.__stash.remove_git_branches(
                                self.__settings['stash']['project'],
                                r,
                                b,
                                c)
                    )
                else:
                    result.add_error_message(
                                'Git branch {} {} is not merged.'
                                .format(repo, branchname))

        return result

    def __search_bamboo(self, key):
        result = SearchResult('BAMBOO')
        branches = []
        for plankey in self.__settings['bamboo']['plans']:
            for branch in self.__bamboo.find_matching_branches(plankey, key):
                branches.append(branch)

        if len(branches) == 0:
            result.add_message('No linked Bamboo branch to remove.', None)
        else:
            for (branchid, branchname) in branches:
                result.add_message(
                    'Bamboo branch {} will be removed.'
                    .format(branchname)
                )
                result.add_action(
                    lambda b=branchid: self.__remove_bamboo_branches(b)
                )

        return result

    def __remove_bamboo_branches(self, branchid):
        self.__bamboo.remove_branch(branchid)

    def __search_folders(self, key):
        result = SearchResult('FOLDERS')
        folders = []
        for rootfolder in self.__settings['folders']:
            dirnames = next(os.walk(rootfolder))[1]
            for dirname in fnmatch.filter(dirnames, '*{}*'.format(key)):
                folders.append(os.path.join(rootfolder, dirname))

        if len(folders) == 0:
            result.add_message('No folder to remove.', None)
        else:
            for folder in folders:
                result.add_message(
                    'Folder \'{}\' will be removed.'
                    .format(folder)
                )
                result.add_action(
                    lambda f=folder: self.__remove_folder(f)
                )

        return result

    def __remove_folder(self, folder):
        rmtree(folder)

    def _get_username(self, message):
        userid = message._get_user_id()
        users = message._client.users
        return next(v['name'] for k, v in users.items() if k == userid)


class SearchResult(object):
    def __init__(self, category):
        self.__actions = []
        self.__messages = []
        self.__error = False
        self.__category = category

    def add_action(self, action):
        self.__actions.append(action)

    def add_message_formatted(self, message):
        self.__messages.append(message)

    def add_message(self, text=None, color='good'):
        self.__messages.append(
            self.__format_good_message(self.__category, text, color))

    def add_error_message(self, text):
        self.__error = True
        self.add_message_formatted(
            self.__format_error_message(self.__category, text)
        )

    @property
    def has_error(self):
        return self.__error

    @property
    def actions(self):
        return self.__actions

    @property
    def messages(self):
        return self.__messages

    def __format_good_message(self, category, text, color):
        return {
            'author_name': category,
            'text': text,
            'color': color
        }

    def __format_error_message(self, category, text):
        return {
            'author_name': category,
            'text': '*{}*'.format(text),
            'color': 'danger',
            'mrkdwn_in': ['text']
        }


instance = CleanBot(settings.plugins.cleanbot.searches,
                    jira.instance,
                    bamboo.instance,
                    crucible.instance,
                    stash.Stash(settings.servers.stash))

if (settings.plugins.cleanbot.enabled):
    @respond_to(instance.get_pattern(), re.IGNORECASE)
    def cleanbot_generate_tasks(message, key):
        instance.generate_clean_tasks(message, key)

    @respond_to('CLEAN YES', re.IGNORECASE)
    def cleanbot_execute_tasks(message):
        instance.execute_clean_tasks(message)
