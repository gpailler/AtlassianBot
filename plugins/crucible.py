# coding: utf-8

import re
import json
import requests
from itertools import filterfalse

from slackbot.bot import listen_to
from slackbot.bot import respond_to

from . import settings
import utils.rest as rest
from utils.messages_cache import MessagesCache


class CrucibleBot(object):
    def __init__(self, cache, server, prefixes):
        self.__cache = cache
        self.__server = server
        self.__prefixes = prefixes
        self.__crucible_regex = re.compile(self.get_pattern(), re.IGNORECASE)

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
                message.send_webapi('', json.dumps(attachments))

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

            uncompleted_reviewers = self.__get_uncompleted_reviewers(reviewid)
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
        return ['<@{}>'.format(r['userName']) for r in reviewers]

    def __get_cachekey(self, reviewId, message):
        return reviewId + message.body['channel']


instance = CrucibleBot(MessagesCache(),
                       settings.servers.crucible,
                       settings.plugins.cruciblebot.prefixes)


if (settings.plugins.cruciblebot.enabled):
    @listen_to(instance.get_pattern(), re.IGNORECASE)
    @respond_to(instance.get_pattern(), re.IGNORECASE)
    def cruciblebot(message, _):
        instance.display_reviews(message)
