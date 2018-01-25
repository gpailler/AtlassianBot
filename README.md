# Atlassian Bot
[![Build status](https://ci.appveyor.com/api/projects/status/iuqcblbxb9jyk2pb/branch/master?svg=true)](https://ci.appveyor.com/project/gpailler/atlassianbot/branch/master)
[![codecov.io](https://codecov.io/github/gpailler/AtlassianBot/coverage.svg?branch=master)](https://codecov.io/github/gpailler/AtlassianBot?branch=master)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/gpailler/AtlassianBot/blob/master/LICENSE)

Atlassian Bot is a collection of plugins to integrate Atlassian tools into Slack.


## Installation
```bash
> git clone https://github.com/gpailler/AtlassianBot.git
> cd AtlassianBot

> pip install virtualenv
> virtualenv venv --python=python3.6
> source venv/bin/activate

> pip install -r requirements.txt
```

## Configuration
### Generate Slack bot API token
Go to https://api.slack.com/bot-users and create a new bot

Copy `local_settings-sample.py` to `local_settings.py` and fill the bot token

### Configure Atlassian bot
Copy `plugins/settings-sample.yml` to `plugins/settings.yml` and activate/configure each bot according your needs


## Launch
```
> python run.py
```

## Plugins
### JiraBot
This plugin reads messages on channels on which he's invited and gives details when he finds a Jira key in a message. Displayed details are the summary, the description and the issue type. The summary is also a link to access issue on Jira.

![jirabot](https://cloud.githubusercontent.com/assets/3621529/14035446/38b7370e-f269-11e5-8539-21daafcc27be.jpg)

### CrucibleBot
This plugin reads messages on channels on which he's invited and gives details when he finds a Review key in a message. Displayed details are the summary and the uncompleted reviewers. If reviewers have same username on Crucible and Slack, they are mentionned to get their attention. The summary is also a link to access review on Crucible.

![cruciblebot](https://cloud.githubusercontent.com/assets/3621529/14035445/38ac86c4-f269-11e5-87c0-362849abf067.jpg)

### BambooBot
This plugin reads messages on which he's mentionned (or direct messages). He is able to move a build plan (and all the related jobs) on top of the build queue. It's useful when all build agents are busy and you want to give priority to you build.

![bamboobot](https://cloud.githubusercontent.com/assets/3621529/14035858/1018335c-f26e-11e5-99a6-0f4105c015ed.jpg)

### JiraNotifier
This plugin send a message on a specific channel when a Jira task is closed. It can be used to notify a team when a story is closed for example.

### CleanBot
This plugin reads messages on which he's mentionned (or direct messages). He analyzes Jira, Crucible, Bamboo and Stash to give a status of a specific Jira task. He checks if related code reviews are closed, and if related Stash branches are merged. If user confirms the clean then the plugin closes Jira task (and all subtasks), removes merged Stash branches, removes Bamboo branches and can remove some specific folders.

