# coding: utf-8

import re
import requests

from slackbot.bot import respond_to

from . import settings
from utils import rest


class BambooBot(object):
    def __init__(self, server, prefixes):
        self.__server = server
        self.__prefixes = prefixes

    def get_pattern(self):
        bamboo_prefixes = '|'.join(self.__prefixes)
        plan_regex = '(?P<plan>(?:{})-[\w]+)(?:-\d+)?/?'.format(bamboo_prefixes)
        deployment_regex = 'viewDeploymentResult.action\?deploymentResultId=(?P<deployment>\d+)'
        return '^UP .*\<?(?:{}|{})\>?'\
            .format(plan_regex, deployment_regex)

    def move_deployment(self, message, deploymentid):
        key = self.__get_deployment_key(deploymentid)
        if key is None:
            message.reply_webapi('Deployment {} doesn\'t exists'.format(deploymentid))
            return
        else:
            message.reply_webapi('Yes my lord. I\'m looking for deployment plan to move...')
            moved = self.__move_top(key, 'DEPLOYMENT')
            if moved:
                message.reply_webapi('Moved deployment {}'.format(deploymentid))
            else:
                message.reply_webapi('Unable to move deployment {} '.format(deploymentid))

    def move_plan(self, message, plankey):
        if self.__plan_exist(plankey) is False:
            message.reply_webapi('Plan {} doesn\'t exists'.format(plankey))
            return

        message.reply_webapi('Yes my lord. I\'m looking for jobs to move...')

        builds = self.__get_builds()
        if builds is not None:
            resultkeys = list(self.__find_matching_builds(builds, plankey))
            if resultkeys:
                for resultkey, index in resultkeys[::-1]:
                    self.__move_top(resultkey, 'BUILD')

                message.reply_webapi('Moved {} jobs'.format(len(resultkeys)))
            else:
                message.reply_webapi('Plan {} not found in queue'
                                     .format(plankey))
        else:
            message.reply_webapi(
                'I\'m not a Bamboo administrator and cannot move jobs')

    def __move_top(self, resultkey, type):
        request = rest.post(
            self.__server,
            '/build/admin/ajax/reorderBuild.action',
            data={
                'resultKey': resultkey,
                'prevResultKey': '',
                'itemType': type
            }
        )

        if request.status_code == requests.codes.ok:
            json = request.json()
            if json['status'] == 'OK':
                return True

            # Deployment plan cannot be moved
            if json['status'] == 'ERROR' and json['errors'][0] == 'Queue out of order':
                return False

            raise Exception('Unknown error')
        elif request.status_code == requests.codes.server_error:
            raise Exception('Not authorized')
        else:
            request.raise_for_status()

    def __plan_exist(self, plankey):
        request = rest.get(
            self.__server,
            '/rest/api/latest/plan/{}'.format(plankey))
        if request.status_code == requests.codes.ok:
            return True
        elif request.status_code != 404:
            request.raise_for_status()

        return False

    def __get_deployment_key(self, deploymentid):
        request = rest.get(
            self.__server,
            '/rest/api/latest/deploy/result/{}'.format(deploymentid))
        if request.status_code == requests.codes.ok:
            return request.json()['key']['key']
        elif request.status_code != 404:
            request.raise_for_status()

        return None

    def find_matching_branches(self, plankey, searched_term):
        request = rest.get(
            self.__server,
            '/rest/api/latest/search/branches',
            data={
                'masterPlanKey': plankey,
                'searchTerm': searched_term
            }
        )

        if request.status_code != requests.codes.ok:
            request.raise_for_status()

        for result in request.json()['searchResults']:
            result = result['searchEntity']
            yield (result['id'],
                   '{}/{}'.format(
                        result['planName'],
                        result['branchName']))

    def remove_branch(self, plankey):
        request = rest.post(
            settings.servers.bamboo,
            '/chain/admin/deleteChain!doDelete.action',
            data={
                'buildKey': plankey,
                'save': 'Confirm'
            }
        )

        if request.status_code == requests.codes.server_error:
            raise Exception('Not authorized')
        elif request.status_code != requests.codes.ok:
            request.raise_for_status()

    def __find_matching_builds(self, builds, plankey):
        for build in builds:
            if build['status'] == 'QUEUED' and 'planKey' in build\
                    and build['planKey'].lower() == plankey.lower():
                yield (build['resultKey'], build['queueIndex'])

    def __get_builds(self):
        request = rest.get(
            self.__server,
            '/build/admin/ajax/getDashboardSummary.action')
        if request.status_code == requests.codes.ok:
            return request.json()['builds']
        elif request.status_code != 403:
            request.raise_for_status()

        return None


instance = BambooBot(settings.servers.bamboo,
                     settings.plugins.bamboobot.prefixes)

if (settings.plugins.bamboobot.enabled):
    @respond_to(instance.get_pattern(), re.IGNORECASE)
    def bamboobot(message, plankey, other):
        result = re.search(instance.get_pattern(), message.body['text'], re.IGNORECASE)

        plankey = result.group('plan')
        if plankey is not None:
            instance.move_plan(message, plankey)

        deployment = result.group('deployment')
        if deployment is not None:
            instance.move_deployment(message, deployment)
