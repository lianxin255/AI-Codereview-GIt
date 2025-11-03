import os
import time
import requests
import fnmatch
from urllib.parse import urljoin
from biz.utils.log import logger


def filter_changes(changes: list) -> list:
    supported_extensions = os.getenv('SUPPORTED_EXTENSIONS', '').split(',')
    filtered_changes = [
        change for change in changes
        if any(change.get('new_path', '').endswith(ext) for ext in supported_extensions)
    ]
    return filtered_changes


class PullRequestHandler:
    def __init__(self, webhook_data: dict, gitea_token: str, gitea_url: str):
        self.pull_request_index = None
        self.webhook_data = webhook_data
        self.gitea_token = gitea_token
        self.gitea_url = gitea_url
        self.action = None
        self.repo_owner = None
        self.repo_name = None
        self.parse_pull_request_event()

    def parse_pull_request_event(self):
        self.action = self.webhook_data.get('action')
        pull_request = self.webhook_data.get('pull_request', {})
        self.pull_request_index = pull_request.get('number')
        base = pull_request.get('base', {})
        repo = base.get('repo', {})
        self.repo_owner = repo.get('owner', {}).get('login')
        self.repo_name = repo.get('name')

    def get_pull_request_changes(self) -> list:
        max_retries = 3
        retry_delay = 10
        for attempt in range(max_retries):
            url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/pulls/{self.pull_request_index}/files"
            headers = {
                'Authorization': f'token {self.gitea_token}',
                'Content-Type': 'application/json'
            }
            response = requests.get(url, headers=headers, verify=False)
            logger.debug(f"Get PR files from Gitea (attempt {attempt + 1}): {response.status_code}, {response.text}")

            if response.status_code == 200:
                files = response.json()
                if files:
                    changes = []
                    for file in files:
                        changes.append({
                            'old_path': file.get('filename'),
                            'new_path': file.get('filename'),
                            'diff': file.get('patch', '')
                        })
                    return changes
                else:
                    logger.info(f"Files is empty, retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
            else:
                logger.warn(f"Failed to get PR files from Gitea: {response.status_code}, {response.text}")
                return []

        logger.warning(f"Max retries ({max_retries}) reached. Files is still empty.")
        return []

    def get_pull_request_commits(self) -> list:
        url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/pulls/{self.pull_request_index}/commits"
        headers = {
            'Authorization': f'token {self.gitea_token}'
        }
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Get PR commits from Gitea: {response.status_code}, {response.text}")

        if response.status_code == 200:
            return response.json()
        else:
            logger.warn(f"Failed to get PR commits: {response.status_code}, {response.text}")
            return []

    def add_pull_request_comment(self, review_result):
        url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/issues/{self.pull_request_index}/comments"
        headers = {
            'Authorization': f'token {self.gitea_token}',
            'Content-Type': 'application/json'
        }
        data = {
            'body': review_result
        }
        response = requests.post(url, headers=headers, json=data, verify=False)
        logger.debug(f"Add comment to Gitea PR: {response.status_code}, {response.text}")
        if response.status_code == 201:
            logger.info("Comment successfully added to pull request.")
        else:
            logger.error(f"Failed to add comment: {response.status_code}")
            logger.error(response.text)

    def target_branch_protected(self) -> bool:
        pull_request = self.webhook_data.get('pull_request', {})
        target_branch = pull_request.get('base', {}).get('ref')

        url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/branch_protections"
        headers = {
            'Authorization': f'token {self.gitea_token}'
        }
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Get protected branches from Gitea: {response.status_code}, {response.text}")

        if response.status_code == 200:
            data = response.json()
            return any(fnmatch.fnmatch(target_branch, item['branch_name']) for item in data)
        else:
            logger.warn(f"Failed to get protected branches: {response.status_code}, {response.text}")
            return False


class PushHandler:
    def __init__(self, webhook_data: dict, gitea_token: str, gitea_url: str):
        self.webhook_data = webhook_data
        self.gitea_token = gitea_token
        self.gitea_url = gitea_url
        self.repo_owner = None
        self.repo_name = None
        self.branch_name = None
        self.commit_list = []
        self.parse_push_event()

    def parse_push_event(self):
        repository = self.webhook_data.get('repository', {})
        self.repo_owner = repository.get('owner', {}).get('login')
        self.repo_name = repository.get('name')
        self.branch_name = self.webhook_data.get('ref', '').replace('refs/heads/', '')
        self.commit_list = self.webhook_data.get('commits', [])

    def get_push_commits(self) -> list:
        if not self.commit_list:
            logger.info("No commits found in push event.")
            return []

        commit_details = []
        for commit in self.commit_list:
            commit_info = {
                'message': commit.get('message'),
                'author': commit.get('author', {}).get('name'),
                'timestamp': commit.get('timestamp'),
                'url': commit.get('url'),
            }
            commit_details.append(commit_info)

        logger.info(f"Collected {len(commit_details)} commits from push event.")
        return commit_details

    def add_push_notes(self, message: str):
        if not self.commit_list:
            logger.warn("No commits found to add notes to.")
            return

        last_commit_id = self.commit_list[-1].get('id')
        if not last_commit_id:
            logger.error("Last commit ID not found.")
            return

        url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/commits/{last_commit_id}/comments"
        headers = {
            'Authorization': f'token {self.gitea_token}',
            'Content-Type': 'application/json'
        }
        data = {
            'body': message
        }
        response = requests.post(url, headers=headers, json=data, verify=False)
        logger.debug(f"Add comment to commit {last_commit_id}: {response.status_code}, {response.text}")
        if response.status_code == 201:
            logger.info("Comment successfully added to push commit.")
        else:
            logger.error(f"Failed to add comment: {response.status_code}")
            logger.error(response.text)

    def repository_compare(self, before: str, after: str):
        url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/compare/{before}...{after}"
        headers = {
            'Authorization': f'token {self.gitea_token}'
        }
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Get compare from Gitea: {response.status_code}, {response.text}")

        if response.status_code == 200:
            files = response.json().get('files', [])
            changes = []
            for file in files:
                changes.append({
                    'old_path': file.get('filename'),
                    'new_path': file.get('filename'),
                    'diff': file.get('patch', '')
                })
            return changes
        else:
            logger.warn(f"Failed to get compare: {response.status_code}, {response.text}")
            return []

    def get_push_changes(self) -> list:
        if not self.commit_list:
            logger.info("No commits found in push event.")
            return []

        before = self.webhook_data.get('before', '')
        after = self.webhook_data.get('after', '')

        if before and after:
            if after.startswith('0000000'):
                return []
            if before.startswith('0000000'):
                before = f"{after}^"
            return self.repository_compare(before, after)
        else:
            return []
