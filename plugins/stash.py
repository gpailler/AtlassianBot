# coding: utf-8

import requests
from utils import rest


class Stash(object):
    def __init__(self, server):
        self.__server = server

    def get_stash_branches(self, repos, project, filter):
        results = []
        for repo in repos:
            path = '/rest/api/1.0/projects/{project}/repos/{repo}/branches'\
                    .format(project=project, repo=repo)
            data = {
                'filterText': filter,
                'details': True,
                'limit': 100
            }

            request = rest.get(self.__server, path, data)
            for result in request.json()['values']:
                results.append((
                    repo,
                    result['id'],
                    result['displayId'],
                    result['latestChangeset']))

        return results

    def branch_merged(self, project, basebranches, repo, branch):
        for to in basebranches:
            path = ('/rest/api/1.0/projects/{project}/repos/{repo}/'
                    'compare/changes/').format(project=project, repo=repo)
            data = {
                'from': branch,
                'to': to,
                'limit': 1
            }

            request = rest.get(self.__server, path, data)
            if request.status_code != requests.codes.ok:
                raise Exception(request.text)
            else:
                if request.json()['size'] == 0:
                    return True

        return False

    def remove_git_branches(self, project, repo, branchkey, changeset):
        path = ('/rest/branch-utils/1.0/projects/{project}/repos/{repo}/'
                'branches').format(project=project, repo=repo)
        data = {
            'name': branchkey,
            'endPoint': changeset,
            'dryRun': False
        }

        request = rest.delete(self.__server, path, data)
        if request.status_code != requests.codes.no_content:
            raise Exception(request.text)
