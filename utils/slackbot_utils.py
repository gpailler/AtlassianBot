import inspect

from slackbot.bot import Bot

def get_slackclient():
    stack = inspect.stack()
    for frame in [f[0] for f in stack]:
        if 'self' in frame.f_locals:
            instance = frame.f_locals['self']
            if isinstance(instance, Bot):
                return instance._client

def get_user_by_crucible_handle(slack_client, username, field_code):
    for userid, user in slack_client.users.items():
        try:
            if user['profile']['fields'][field_code]['value'] == username:
                return userid
        except:
            pass
