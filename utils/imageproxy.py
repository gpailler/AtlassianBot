import requests
from base64 import b64encode, b64decode


def converturl_proxyurl(server, url):
    icon_request = requests.get(url)
    if icon_request.status_code == requests.codes.ok:
        content_type = icon_request.headers.get('Content-Type')
        content_type = __encode(content_type.encode())
        content = __encode(icon_request.content)

        return '%s/image/%s/%s' % (server, content_type, content)

    return url


def convertdata_proxyurl(server, content_type, data):
    content_type = __encode(content_type.encode())
    content = data.replace('+', '-').replace('/', '_')

    return '%s/image/%s/%s' % (server, content_type, content)


def decode(content):
    return b64decode(content.encode(), altchars='-_')


def __encode(content):
    return b64encode(content, altchars=b'-_').decode()
