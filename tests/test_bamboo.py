import json
import pytest
import re
import requests
from urllib.parse import parse_qs

from .common import get_message, controlled_responses
from plugins.bamboo import BambooBot

with open('tests/test_bamboo_data.json') as data_file:
    data = json.load(data_file)

server = {'host': 'http://host', 'username': 'user', 'password': 'pass'}
prefixes = ['BAMA', 'BAMB']


@pytest.fixture
def bot():
    bamboobot = BambooBot(server, prefixes)
    return bamboobot


@pytest.mark.parametrize('input,expected', [
    ('', None),
    ('BAMA', None),
    ('BAMA-', None),
    ('ABAMA-DEV', None),
    ('AMA-DEV', None),
    ('SOMETHING BAMA-DEV', None),
    ('UP BAMA-DEV', 'BAMA-DEV'),
    ('UP BAMA-DEV SOMETHING', 'BAMA-DEV'),
    ('UP SOMETHING BAMA-DEV SOMETHING', 'BAMA-DEV'),
    ('SOMETHING UP BAMA-DEV SOMETHING', None),
    ('UP http://host/browse/BAMA-DEV', 'BAMA-DEV'),
    ('UP http://host/browse/BAMA-DEV-JOB-123', 'BAMA-DEV'),
    ('UP http://host/browse/BAMA-DEV123-123', 'BAMA-DEV123'),
    ('UP http://host/browse/BAMA-DEV123-JOB-123', 'BAMA-DEV123'),
    ('UP http://host/deploy/viewDeploymentResult.action?deploymentResultId=123456789', '123456789'),
])
def test_bamboopattern(bot, input, expected):
    result = re.search(bot.get_pattern(), input, re.IGNORECASE)
    if expected is None:
        assert result == expected
    else:
        plan = result.group('plan')
        if plan is not None:
            assert plan == expected

        deployment = result.group('deployment')
        if deployment is not None:
            assert deployment == expected


@pytest.mark.parametrize('testdata', [
                        (data['move_plan_notexist']),
                        (data['move_plan_notadmin']),
                        (data['move_plan_notinqueue'])
                        ])
def test_move_plan_error(bot, testdata):
    with controlled_responses(testdata['requests'], server):
        msg = get_message()
        bot.move_plan(msg, 'BAMA-DEV')

        [msg.send_webapi.assert_any_call(x, attachments=None, as_user=True) for x in testdata['result']]


@pytest.mark.parametrize('testdata', [
                        (data['move_plan_planexist_error']),
                        (data['move_plan_builds_error']),
                        ])
def test_move_plan_planexist_exception(bot, testdata):
    with controlled_responses(testdata['requests'], server):
        with pytest.raises(requests.exceptions.HTTPError):
            msg = get_message()
            bot.move_plan(msg, 'BAMA-DEV')


@pytest.mark.parametrize('testdata', [
                        (data['move_plan_inqueue'])
                        ])
def test_move_plan(bot, testdata):
    with controlled_responses(testdata['requests'], server) as rsps:
        for x in range(0, len(testdata['post_result'])):
            rsps.add_post(
                'http://host/build/admin/ajax/reorderBuild.action',
                200,
                {'status': 'OK'})

        msg = get_message()
        bot.move_plan(msg, 'BAMA-DEV')

        offset = len(testdata['requests'])
        for index, result in enumerate(testdata['post_result']):
            expDict = parse_qs(
                               result,
                               keep_blank_values=True,
                               strict_parsing=True)
            resDict = parse_qs(
                               rsps.calls[index + offset].request.body,
                               keep_blank_values=True,
                               strict_parsing=True)
            assert expDict == resDict

        [msg.send_webapi.assert_any_call(x, attachments=None, as_user=True) for x in testdata['result']]


@pytest.mark.parametrize('testdata', [
    (data['move_deployment_inqueue'])
])
def test_move_deployment(bot, testdata):
    with controlled_responses(testdata['requests'], server) as rsps:
        rsps.add_post(
            'http://host/build/admin/ajax/reorderBuild.action',
            200,
            {'status': 'OK'})

        msg = get_message()
        bot.move_deployment(msg, '123')

        expDict = parse_qs(
            testdata['post_result'][0],
            keep_blank_values=True,
            strict_parsing=True)
        resDict = parse_qs(
            rsps.calls[1].request.body,
            keep_blank_values=True,
            strict_parsing=True)
        assert expDict == resDict

        [msg.send_webapi.assert_any_call(x, attachments=None, as_user=True) for x in testdata['result']]

@pytest.mark.parametrize('code,status,exception,errmsg', [
    (403, 'OK', requests.exceptions.HTTPError, '403 Client Error: Forbidden for url: http://host/build/admin/ajax/reorderBuild.action'),
    (500, 'OK', Exception, 'Not authorized'),
    (200, 'KO', Exception, 'Unknown error')
])
def test_move_plan_move_exception(bot, code, status, exception, errmsg):
    testdata = data['move_plan_inqueue']
    with controlled_responses(testdata['requests'], server) as rsps:
        rsps.add_post(
            'http://host/build/admin/ajax/reorderBuild.action',
            code,
            {'status': status})

        with pytest.raises(exception) as excinfo:
            msg = get_message()
            bot.move_plan(msg, 'BAMA-DEV')

        assert errmsg == str(excinfo.value)


@pytest.mark.parametrize('testdata', [data['find_matching_branches']])
def test_find_matching_branches(bot, testdata):
    with controlled_responses(testdata['requests'], server):

        result = bot.find_matching_branches(
                                            testdata['plankey'],
                                            testdata['searched_term'])
        result = list(result)
        assert result[0][0] == testdata['result'][0]
        assert result[0][1] == testdata['result'][1]


@pytest.mark.parametrize('testdata', [data['find_matching_branches500']])
def test_find_matching_branches_error(bot, testdata):
    with controlled_responses(testdata['requests'], server):
        with pytest.raises(requests.exceptions.HTTPError):
            list(bot.find_matching_branches(
                                            testdata['plankey'],
                                            testdata['searched_term']))
