import pytest
import json
import re
from mock import MagicMock

from plugins.clean import CleanBot
from plugins.stash import Stash
from .common import get_message, controlled_responses

from . import test_jira
from . import test_bamboo
from . import test_crucible

import logging
logging.basicConfig(level=logging.DEBUG)


with open('tests/test_clean_data.json') as data_file:
    data = json.load(data_file)

with open('tests/test_jira_data.json') as jira_data_file:
    jira_data = json.load(jira_data_file)

def get_message_with_user(input):
    msg = get_message(input)
    msg._get_user_id = MagicMock(return_value='id1')
    msg._client = MagicMock()
    msg._client.users = {'id1': {'name': 'username1'}}

    return msg


@pytest.fixture
def bot():
    jira = test_jira.bot()
    bamboo = test_bamboo.bot()
    crucible = test_crucible.bot()
    stash_settings = {'host': 'http://host', 'username': 'u', 'password': 'p'}
    stash = Stash(stash_settings)

    settings = [{
        'stash': {
            'project': 'stashproject',
            'repos': ['repo1', 'repo2'],
            'basebranches': ['refs/heads/master', 'refs/heads/develop']
        },
        'bamboo': {
            'plans': ['BAMA-MASTER', 'BAMA-DEV']
        },
        'folders': []
    }]
    cleanbot = CleanBot(settings, jira, bamboo, crucible, stash)
    return cleanbot


@pytest.mark.parametrize('input,expected', [
    ('CLEAN ', None),
    ('CLEAN JIRA', None),
    ('CLEAN JIRA-', None),
    ('CLEAN JIRA-1234', 'JIRA-1234'),
    ('CLEAN IRA-1234', None),
    ('SOMETHING JIRA-1234', None),
    ('JIRA-1234 CLEAN', None),
    ('CLEAN JIRA-1234 CLEAN', 'JIRA-1234'),
    ('CLEANJIRA-1234', None),
    ('JIRA-1234CLEAN', None),
    ('CLEAN JIRA-1234 JIRA-5678', 'JIRA-1234'),
])
def test_cleanpattern(bot, input, expected):
    result = re.search(bot.get_pattern(), input, re.IGNORECASE)
    if expected is None:
        assert result == expected
    else:
        assert result.group(1) == expected


@pytest.mark.parametrize('id,result,exception', [
                         ('id1', 'username1', None),
                         ('id2', 'username2', None),
                         ('id3', None, StopIteration)
                         ])
def test_get_username(bot, id, result, exception):
    message = get_message()
    message._get_user_id = MagicMock(return_value=id)
    message._client = MagicMock()
    message._client.users = {
        'id1': {'name': 'username1'},
        'id2': {'name': 'username2'}
        }

    if exception:
        with pytest.raises(exception):
            bot._get_username(message)
    else:
        assert result == bot._get_username(message)


@pytest.mark.parametrize('input,testdata', [
                         ('JIRA-1', data['cleanbot_canclean']),
                         ('JIRA-3', data['cleanbot_issuenotfound']),
                         ('JIRA-1', data['cleanbot_reviewnotclosed']),
                         ('JIRA-1', data['cleanbot_branchnotmerged']),
                         ('JIRA-1', data['cleanbot_storyclosed']),
                         ])
def test_generate_clean_tasks(bot, input, testdata):
    msg = get_message_with_user(input)

    with controlled_responses(jira_data['jira_default_field_query'] + testdata['requests']):

        bot.generate_clean_tasks(msg, input)

        results = testdata['result']
        assert len(msg.send_webapi.call_args_list) == len(results)
        tuples = zip(results, msg.send_webapi.call_args_list)
        for result, (args, kwargs) in tuples:
            if type(result) is list:
                assert args[0] is ''
                assert json.loads(kwargs['attachments']) == result
            else:
                assert result == args[0]
