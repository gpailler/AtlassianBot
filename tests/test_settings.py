# coding: utf-8

from plugins import settings


def test_yaml_parsing():
    assert settings.servers.jira.username == 'usernamewith%'
    assert settings.servers.jira.password == 'password'


def test_yaml_string_interpolation():
    assert settings.servers.jira.username == settings.servers.bamboo.username
    assert settings.servers.jira.password == settings.servers.bamboo.password
