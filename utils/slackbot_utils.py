import inspect

from slackbot.bot import Bot


def get_slackclient():
    stack = inspect.stack()
    for frame in [f[0] for f in stack]:
        if 'self' in frame.f_locals:
            instance = frame.f_locals['self']
            if isinstance(instance, Bot):
                return instance._client