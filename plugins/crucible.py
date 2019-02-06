# coding: utf-8

import re
import json
import requests
from itertools import filterfalse

from slackbot.bot import listen_to
from slackbot.bot import respond_to

from utils import slackbot_utils
from . import settings
from utils import rest
from utils.messages_cache import MessagesCache


class CrucibleBot(object):
    def __init__(self, cache, server, prefixes, slack_client = None, handle_field = None):
        self.__cache = cache
        self.__server = server
        self.__prefixes = prefixes
        self.__handle_field = handle_field
        self.__crucible_regex = re.compile(self.get_pattern(), re.IGNORECASE)
        self.__slackclient = slack_client if slack_client else slackbot_utils.get_slackclient()

    def get_pattern(self):
        crucible_prefixes = '|'.join(self.__prefixes)
        return r'(?:^|\s|[\W]+)((?:{})-[\d]+)(?:$|\s|[\W]+)'\
            .format(crucible_prefixes)

    def display_reviews(self, message):
        def filter_predicate(x):
            return self.__cache.IsInCache(self.__get_cachekey(x, message))

        reviews = self.__crucible_regex.findall(message.body['text'])
        reviews = filterfalse(filter_predicate, reviews)
        if reviews:
            attachments = []
            for reviewid in filterfalse(filter_predicate, reviews):
                self.__cache.AddToCache(self.__get_cachekey(reviewid, message))

                try:
                    msg = self.__get_review_message(reviewid)
                    if msg is None:
                        msg = self.__get_reviewnotfound_message(reviewid)

                    attachments.append(msg)
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 401:
                        print('Invalid auth')

                    raise
            if attachments:
                message.reply_webapi('', json.dumps(attachments))

    def get_reviews_from_jira(self, jirakey):
        request = rest.get(
            self.__server,
            '/rest-service/search-v1/reviewsForIssue',
            {'jiraKey': jirakey})

        if request.status_code == requests.codes.ok:
            return request.json()['reviewData']
        else:
            request.raise_for_status()

    def __get_review_message(self, reviewid):
        review = self.__get_review(reviewid)
        if review:
            reviewurl = '{}/cru/{}'.format(
                   self.__server['host'],
                   reviewid)
            summary = review['name']
            id = review['permaId']['id']

            attachment = {
                'fallback': '{key} - {summary}\n{url}'.format(
                    key=id,
                    summary=summary,
                    url=reviewurl
                    ),
                'author_name': id,
                'author_link': reviewurl,
                'text': summary,
                'color': '#4a6785',
                'fields': [],
            }

            uncompleted_reviewers = list(self.__get_uncompleted_reviewers(reviewid))
            if uncompleted_reviewers:
                attachment['fallback'] = attachment['fallback'] + \
                    '\nUncompleted reviewers: {}'.format(
                    ', '.join(uncompleted_reviewers))
                attachment['fields'].append({
                    'title': 'Uncompleted reviewers',
                    'value': ' '.join(uncompleted_reviewers),
                    'short': False
                })
            return attachment

    def __get_reviewnotfound_message(self, reviewid):
        return {
            'fallback': 'Review {key} not found'.format(key=reviewid),
            'author_name': reviewid,
            'text': ':exclamation: Review not found',
            'color': 'warning'
        }

    def __get_review(self, reviewid):
        request = rest.get(
            self.__server,
            '/rest-service/reviews-v1/{id}'.format(id=reviewid))
        if request.status_code == requests.codes.ok:
            return request.json()
        elif request.status_code != 404:
            request.raise_for_status()

    def __get_uncompleted_reviewers(self, reviewid):
        request = rest.get(
            self.__server,
            '/rest-service/reviews-v1/{id}/reviewers/uncompleted'
            .format(id=reviewid))

        reviewers = request.json()['reviewer']
        for r in reviewers:
            user_id = self.__slackclient.find_user_by_name(r['userName'])
            if not user_id and self.__handle_field:
                user_id = slackbot_utils.get_user_by_crucible_handle(self.__slackclient, r['userName'], self.__handle_field)
            yield '<@{}>'.format(user_id) if user_id else '@{}'.format(r['userName'])

    def __get_cachekey(self, reviewId, message):
        return reviewId + message.body['channel']


instance = CrucibleBot(MessagesCache(),
                       settings.servers.crucible,
                       settings.plugins.cruciblebot.prefixes,
                       handle_field=settings.plugins.cruciblebot.handlefield)


if (settings.plugins.cruciblebot.enabled):
    @listen_to(instance.get_pattern(), re.IGNORECASE)
    @respond_to(instance.get_pattern(), re.IGNORECASE)
    def cruciblebot(message, _):
        instance.display_reviews(message)
