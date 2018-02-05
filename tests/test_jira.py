import pytest
from mock import MagicMock, mock
import responses
import re
import json
from threading import Event

import utils.notifier_bot as notifier_bot
from .common import controlled_responses, get_message
from plugins.jira import JiraBot, JiraNotifierBot
from utils.messages_cache import MessagesCache


with open('tests/test_jira_data.json') as data_file:
    data = json.load(data_file)

jira_server = {
    'host': 'http://host',
    'username': 'user',
    'password': 'pass'
    }

imageproxy_server = {
    'host': 'http://imageproxy'
    }

prefixes = ['JIRA', 'JIRB']


@pytest.fixture
def bot():
    jiraBot = JiraBot(
                      MessagesCache(),
                      jira_server,
                      imageproxy_server,
                      prefixes)
    return jiraBot


@pytest.mark.parametrize('input,expected', [
    ('', None),
    ('JIRA', None),
    ('JIRA-', None),
    ('JIRA-1234', 'JIRA-1234'),
    ('IRA-1234', None),
    ('SOMETHING JIRA-1234', 'JIRA-1234'),
    ('JIRA-1234 SOMETHING', 'JIRA-1234'),
    ('SOMETHING JIRA-1234 SOMETHING', 'JIRA-1234'),
    ('SOMETHINGJIRA-1234', None),
    ('JIRA-1234SOMETHING', None),
    ('CLEAN JIRA-1234', None),
])
def test_jirapattern(bot, input, expected):
    result = re.search(bot.get_pattern(), input, re.IGNORECASE)
    if expected is None:
        assert result == expected
    else:
        assert result.group(1) == expected


@pytest.mark.parametrize('input,testdata', [
                         ('JIRA-1 & JIRA-2', data['jirabot_result']),
                         ('JIRA-1 & JIRA-1', data['jirabot_result1']),
                         ('JIRA-3', data['jirabot_notexist']),
                         ])
def test_display_issues(bot, input, testdata):
    with controlled_responses(data['jira_default_field_query'] + testdata['requests']) as rsps:
        message = get_message(input)

        bot.display_issues(message)

        assert len(message.send_webapi.call_args_list) == 1
        args, kwargs = message.send_webapi.call_args_list[0]
        assert args[0] is ''
        assert json.loads(args[1]) == testdata['result']


@pytest.mark.parametrize('input,testdata', [
                         ('JIRA-1', data['jirabot_result1']),
                         ('JIRA-3', data['jirabot_notexist']),
                         ])
def test_messages_cache(bot, input, testdata):
    with controlled_responses(data['jira_default_field_query'] + testdata['requests']):
        # First call should display message
        message = get_message(input, channel='channel1')
        bot.display_issues(message)
        assert message.send_webapi.called

        # Second call on same channel should not display message again
        message = get_message(input, channel='channel1')
        bot.display_issues(message)
        assert not message.send_webapi.called

    with controlled_responses(testdata['requests']):
        # Call on another channel should display the message again
        message = get_message(input, channel='channel2')
        bot.display_issues(message)
        assert message.send_webapi.called


def test_wrong_auth(bot):
    with controlled_responses(data['jira_default_field_query']) as rsps:
        rsps.rsps.add(
            responses.GET,
            'http://host/rest/api/2/issue/JIRA-1',
            status=401)

        message = get_message('JIRA-1')
        bot.display_issues(message)

        assert len(message.send_webapi.call_args_list) == 1
        args, kwargs = message.send_webapi.call_args_list[0]
        assert args[0] is ''
        assert json.loads(args[1]) == [{
                'color': 'danger',
                'fallback': 'Jira authentication error',
                'text': ':exclamation: Jira authentication error'}]


@pytest.mark.parametrize('testdata', [
                         (data['jiranotifier_changelog_with_assignee']),
                         (data['jiranotifier_changelog_without_assignee'])
                         ])
def test_notifier(testdata):
    slack_mock = MagicMock()
    slack_mock.find_user_by_name = MagicMock(side_effect=lambda x: x)
    slack_mock.channels = {'channel_id': {'name': 'atlassianbot-test'}}
    slack_mock.send_message = MagicMock()

    conf = {
        "polling_interval": 1,
        "notifiers":
        [
            {
                "query": "project = JIRA and status = Closed and issuetype not in subtaskIssueTypes()",
                "channel": "atlassianbot-test"
            }
        ]
    }

    with controlled_responses(data['jira_default_field_query'] + testdata['requests'][1:]) as rsps:
        rsps.rsps.add(
            responses.GET,
            re.compile(r'http?://host/rest/api/2/search.+'),
            status=200,
            body=json.dumps(testdata['requests'][0]['text']),
            content_type='application/json')

        rsps.rsps.add(
            responses.GET,
            re.compile(r'http?://host/rest/api/2/search.+'),
            status=200,
            body=json.dumps(testdata['requests'][0]['text']),
            content_type='application/json')

        with JiraNotifierBot(jira_server, imageproxy_server, conf, slack_mock) as obj:
            assert len(obj._jobs) == 1
            event = Event()

            def notifier_run():
                event.set()

            obj._jobs[0].run_callback = notifier_run
            assert event.wait(timeout=5) is True

            slack_mock.send_message.assert_called_once_with(
                                                        'channel_id',
                                                        '',
                                                        attachments=mock.ANY)
            call = slack_mock.send_message.call_args
            call_args, call_kwargs = call
            assert testdata['result'] == json.loads(call_kwargs['attachments'])
