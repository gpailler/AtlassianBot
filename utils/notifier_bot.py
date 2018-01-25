import abc
import inspect
import json
import logging
import threading

from concurrent.futures import ThreadPoolExecutor
from slackbot.bot import Bot

from utils import slackbot_utils

logger = logging.getLogger(__name__)

MAX_NOTIFIERS_WORKERS = 2


class NotifierBot(object):
    def __init__(self, slackclient=None):
        logger.info('registered %s', self.__class__.__name__)

        self.__slackclient = slackclient if slackclient else slackbot_utils.get_slackclient()

        if self.__slackclient is None:
            logger.error('Unable to retrieve slackclient instance')
            return

        self.executor = ThreadPoolExecutor(max_workers=MAX_NOTIFIERS_WORKERS)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.executor.shutdown(wait=True)

    def submit(self, job):
        job._init_threaded(self.executor, self.__slackclient)


class NotifierJob(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, channel, polling_interval):
        self.channel = channel
        self.polling_interval = polling_interval
        self.run_callback = None

    def _init(self):
        try:
            self.init()
        except Exception as ex:
            logger.error('Unable to init notifier job: %s', ex, exc_info=True)

    def _run(self):
        try:
            self.run()

            if self.run_callback is not None:
                self.run_callback()
        except Exception as ex:
            logger.error('Unable to run notifier job: %s', ex, exc_info=True)

    def __run_async(self, fn):
        threading.Timer(self.polling_interval, self._run_in_executor).start()

    def _run_in_executor(self):
        try:
            self.__executor \
                .submit(self._run) \
                .add_done_callback(self.__run_async)
        except RuntimeError as ex:
            logger.warn('Unable to run task: %s', ex, exc_info=True)

    def _init_threaded(self, executor, slackclient):
        self.__executor = executor
        self.__slackclient = slackclient
        self.__channel_id = self.__get_channel(self.channel)
        if self.__channel_id is None:
            logger.error('Unable to find channel')
            return

        self.__executor \
            .submit(self._init) \
            .add_done_callback(self.__run_async)

    def __get_channel(self, channelname):
        for id, channel in list(self.__slackclient.channels.items()):
            if channel.get('name', None) == channelname:
                return id

    @abc.abstractmethod
    def init(self):
        """Method that should do something."""

    @abc.abstractmethod
    def run(self):
        """Method that should do something."""

    def send_message(self, attachments):
        self.__slackclient.send_message(
                self.__channel_id,
                '',
                attachments=json.dumps(attachments))
