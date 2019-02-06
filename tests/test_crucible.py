import base64
import json
import pytest
import re
import requests
from mock import MagicMock

from .common import get_message, controlled_responses
from plugins.crucible import CrucibleBot
from utils.messages_cache import MessagesCache

with open('tests/test_crucible_data.json') as data_file:
    data = json.load(data_file)

server = {'host': 'http://host', 'username': 'user', 'password': 'pass'}
userpass = server['username'] + ':' + server['password']
userpass = base64.b64encode(userpass.encode()).decode()
prefixes = ['CRUA', 'CRUB']


@pytest.fixture
def bot():
    slack_mock = MagicMock()
    slack_mock.find_user_by_name = MagicMock(side_effect=lambda x: x)

    cruciblebot = CrucibleBot(MessagesCache(), server, prefixes, slack_mock)
    return cruciblebot


@pytest.mark.parametrize('input,expected', [
    ('', None),
    ('CRUA', None),
    ('CRUA-', None),
    ('CRUA-1234', 'CRUA-1234'),
    ('CRUB-1234', 'CRUB-1234'),
    ('KCRUA-1234', None),
    ('SOMETHING CRUA-1234', 'CRUA-1234'),
    ('CRUA-1234 SOMETHING', 'CRUA-1234'),
    ('SOMETHING CRUA-1234 SOMETHING', 'CRUA-1234'),
    ('SOMETHINGCRUA-1234', None),
    ('CRUA-1234SOMETHING', None),
])
def test_cruciblepattern(bot, input, expected):
    result = re.search(bot.get_pattern(), input, re.IGNORECASE)
    if expected is None:
        assert result == expected
    else:
        assert result.group(1) == expected


@pytest.mark.parametrize('input,testdata', [
                         ('CRUA-1', data['display_reviews_CRUA-1']),
                         ('CRUA-2', data['display_reviews_CRUA-2']),
                         ('CRUA-1 & CRUA-2', data['display_reviews_CRUA-1&2']),
                         ('CRUA-1 & CRUA-1', data['display_reviews_CRUA-11']),
                         ])
def test_display_reviews(bot, input, testdata):
    with controlled_responses(testdata['requests'], server):
        message = get_message(input)

        bot.display_reviews(message)

        assert len(message.send_webapi.call_args_list) == 1
        args, kwargs = message.send_webapi.call_args_list[0]
        assert args[0] is ''
        assert json.loads(kwargs['attachments']) == testdata['result']


@pytest.mark.parametrize('input,testdata', [
                         ('CRUA-1', data['display_reviews_CRUA-1']),
                         ('CRUA-2', data['display_reviews_CRUA-2']),
                         ])
def test_messages_cache(bot, input, testdata):
    with controlled_responses(testdata['requests']):
        # First call should display message
        message = get_message(input, channel='channel1')
        bot.display_reviews(message)
        assert message.send_webapi.called

        # Second call on same channel should not display message again
        message = get_message(input, channel='channel1')
        bot.display_reviews(message)
        assert not message.send_webapi.called

    with controlled_responses(testdata['requests']):
        # Call on another channel should display the message again
        message = get_message(input, channel='channel2')
        bot.display_reviews(message)
        assert message.send_webapi.called


@pytest.mark.parametrize('input,testdata', [
                         ('CRUA-3', data['display_reviews_CRUA-3-error1']),
                         ('CRUA-3', data['display_reviews_CRUA-3-error2']),
                         ])
def test_display_reviews_error(bot, input, testdata):
    with controlled_responses(testdata['requests'], server):
        message = get_message(input)

        with pytest.raises(requests.exceptions.HTTPError):
            bot.display_reviews(message)


@pytest.mark.parametrize('jirakey,testdata', [
    ('JIRAA-1', data['get_reviews_from_jira'])
])
def test_get_reviews_from_jira(bot, jirakey, testdata):
    with controlled_responses(testdata['requests'], server):

        result = bot.get_reviews_from_jira(jirakey)
        reviews = [r['permaId']['id'] for r in result]
        assert reviews == testdata['result']


@pytest.mark.parametrize('jirakey,testdata', [
    ('JIRAA-2', data['get_reviews_from_jira-error'])
])
def test_get_reviews_from_jira_err(bot, jirakey, testdata):
    with controlled_responses(testdata['requests'], server):
        with pytest.raises(requests.exceptions.HTTPError):
            bot.get_reviews_from_jira(jirakey)
