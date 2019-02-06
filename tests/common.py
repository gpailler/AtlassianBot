import base64
import json
import responses
from mock import MagicMock
from slackbot.dispatcher import Message


def get_message(text=None, channel='channelid', thread_ts=None):
    message = Message(None, {'channel': channel, 'text': text, 'thread_ts': thread_ts})
    message.send_webapi = MagicMock()
    return message


class controlled_responses(object):
    def __init__(self, requests_get=[], server=None):
        self.requests_get = requests_get
        self.server = server

    def __enter__(self):
        self.rsps = responses.RequestsMock()
        self.rsps.__enter__()
        self.__add_responses()

        return self

    def __exit__(self, type, value, traceback):
        if self.server:
            self.__validate_auth_header()
        self.rsps.__exit__(type, value, traceback)

    @property
    def calls(self):
        return self.rsps.calls

    def add_post(self, url, status, body):
        self.rsps.add(
            responses.POST,
            url,
            status=status,
            body=json.dumps(body),
            content_type='application/json')

    def __add_responses(self):
        for request in self.requests_get:
            body = None
            content_type = 'application/json'

            if 'content_type' in request:
                content_type = request['content_type']

            if 'text' in request:
                if content_type.startswith('image/'):
                    body = base64.b64decode(request['text'])
                else:
                    body = json.dumps(request['text'])

            self.rsps.add(
                responses.GET,
                request['url'],
                status=request['code'],
                body=body,
                content_type=content_type,
                match_querystring=True)

    def __validate_auth_header(self):
        userpass = self.server['username'] + ':' + self.server['password']
        userpass = base64.b64encode(userpass.encode()).decode()
        for call in self.rsps.calls:
            assert call.request.headers['Authorization'] == 'Basic ' + userpass
