import os
import time
import requests
import fnmatch
from urllib.parse import urljoin
from biz.utils.log import logger


def filter_changes(changes: list) -> list:
    supported_extensions_str = os.getenv("SUPPORTED_EXTENSIONS", "")
    if not supported_extensions_str:
        logger.warning(
            "SUPPORTED_EXTENSIONS environment variable is not set or empty. No changes will be filtered."
        )
        return []

    supported_extensions = [
        ext.strip() for ext in supported_extensions_str.split(",") if ext.strip()
    ]
    if not supported_extensions:
        logger.warning(
            "SUPPORTED_EXTENSIONS is empty after parsing. No changes will be filtered."
        )
        return []

    logger.info(f"Filtering changes with supported extensions: {supported_extensions}")
    filtered_changes = []
    for change in changes:
        new_path = change.get("new_path", "")
        if any(new_path.endswith(ext) for ext in supported_extensions):
            filtered_changes.append(change)
            logger.debug(f"File {new_path} matches supported extensions")
        else:
            logger.debug(
                f"File {new_path} does not match supported extensions, filtered out"
            )

    logger.info(f"Filtered {len(filtered_changes)} out of {len(changes)} changes")
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
        self.action = self.webhook_data.get("action")
        pull_request = self.webhook_data.get("pull_request", {})
        self.pull_request_index = pull_request.get("number")
        base = pull_request.get("base", {})
        repo = base.get("repo", {})
        self.repo_owner = repo.get("owner", {}).get("login")
        self.repo_name = repo.get("name")

    def get_pull_request_changes(self) -> list:
        max_retries = 3
        retry_delay = 10
        for attempt in range(max_retries):
            url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/pulls/{self.pull_request_index}/files"
            headers = {
                "Authorization": f"token {self.gitea_token}",
                "Content-Type": "application/json",
            }
            response = requests.get(url, headers=headers, verify=False)
            logger.debug(
                f"Get PR files from Gitea (attempt {attempt + 1}): {response.status_code}, {response.text}"
            )

            if response.status_code == 200:
                files = response.json()
                if files:
                    changes = []
                    for file in files:
                        # Gitea API may not include patch in files endpoint response
                        # Try to get patch from the file data, if not available, fetch diff separately
                        patch = file.get("patch", "")
                        
                        # If patch is empty, try to get diff from .diff endpoint
                        if not patch:
                            diff_url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/pulls/{self.pull_request_index}.diff"
                            try:
                                diff_response = requests.get(diff_url, headers=headers, verify=False)
                                if diff_response.status_code == 200:
                                    full_diff = diff_response.text
                                    # Extract diff for this specific file from the full diff
                                    filename = file.get("filename")
                                    if filename and filename in full_diff:
                                        # Simple extraction - find the diff section for this file
                                        patch = self._extract_file_diff(full_diff, filename)
                                        logger.debug(f"Fetched diff for {filename} from .diff endpoint")
                                else:
                                    logger.warning(f"Failed to fetch diff from .diff endpoint: {diff_response.status_code}")
                            except Exception as e:
                                logger.warning(f"Error fetching diff from .diff endpoint: {e}")
                        
                        changes.append(
                            {
                                "old_path": file.get("filename"),
                                "new_path": file.get("filename"),
                                "diff": patch,
                                "additions": file.get("additions", 0),
                                "deletions": file.get("deletions", 0),
                            }
                        )
                    logger.info(f"Retrieved {len(changes)} file changes from PR")
                    return changes
                else:
                    logger.info(
                        f"Files is empty, retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(retry_delay)
            else:
                logger.warn(
                    f"Failed to get PR files from Gitea: {response.status_code}, {response.text}"
                )
                return []

        logger.warning(f"Max retries ({max_retries}) reached. Files is still empty.")
        return []

    def _extract_file_diff(self, full_diff: str, filename: str) -> str:
        """Extract diff content for a specific file from the full diff text"""
        lines = full_diff.split('\n')
        result_lines = []
        in_file = False
        
        for line in lines:
            # Check if this is the start of our file's diff
            if line.startswith('diff --git') and filename in line:
                in_file = True
                result_lines.append(line)
            elif in_file:
                # Check if we've hit the next file's diff
                if line.startswith('diff --git'):
                    break
                result_lines.append(line)
        
        return '\n'.join(result_lines) if result_lines else ""

    def get_pull_request_commits(self) -> list:
        url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/pulls/{self.pull_request_index}/commits"
        headers = {"Authorization": f"token {self.gitea_token}"}
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(
            f"Get PR commits from Gitea: {response.status_code}, {response.text}"
        )

        if response.status_code == 200:
            return response.json()
        else:
            logger.warn(
                f"Failed to get PR commits: {response.status_code}, {response.text}"
            )
            return []

    def add_pull_request_comment(self, review_result):
        url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/issues/{self.pull_request_index}/comments"
        headers = {
            "Authorization": f"token {self.gitea_token}",
            "Content-Type": "application/json",
        }
        data = {"body": review_result}
        response = requests.post(url, headers=headers, json=data, verify=False)
        logger.debug(
            f"Add comment to Gitea PR: {response.status_code}, {response.text}"
        )
        if response.status_code == 201:
            logger.info("Comment successfully added to pull request.")
        else:
            logger.error(f"Failed to add comment: {response.status_code}")
            logger.error(response.text)

    def target_branch_protected(self) -> bool:
        pull_request = self.webhook_data.get("pull_request", {})
        target_branch = pull_request.get("base", {}).get("ref")

        url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/branch_protections"
        headers = {"Authorization": f"token {self.gitea_token}"}
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(
            f"Get protected branches from Gitea: {response.status_code}, {response.text}"
        )

        if response.status_code == 200:
            data = response.json()
            return any(
                fnmatch.fnmatch(target_branch, item["branch_name"]) for item in data
            )
        else:
            logger.warn(
                f"Failed to get protected branches: {response.status_code}, {response.text}"
            )
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
        repository = self.webhook_data.get("repository", {})
        self.repo_owner = repository.get("owner", {}).get("login")
        self.repo_name = repository.get("name")
        self.branch_name = self.webhook_data.get("ref", "").replace("refs/heads/", "")
        self.commit_list = self.webhook_data.get("commits", [])

    def get_push_commits(self) -> list:
        if not self.commit_list:
            logger.info("No commits found in push event.")
            return []

        commit_details = []
        for commit in self.commit_list:
            commit_info = {
                "message": commit.get("message"),
                "author": commit.get("author", {}).get("name"),
                "timestamp": commit.get("timestamp"),
                "url": commit.get("url"),
            }
            commit_details.append(commit_info)

        logger.info(f"Collected {len(commit_details)} commits from push event.")
        return commit_details

    def add_push_notes(self, message: str):
        if not self.commit_list:
            logger.warn("No commits found to add notes to.")
            return

        last_commit_id = self.commit_list[-1].get("id")
        if not last_commit_id:
            logger.error("Last commit ID not found.")
            return

        url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/commits/{last_commit_id}/comments"
        headers = {
            "Authorization": f"token {self.gitea_token}",
            "Content-Type": "application/json",
        }
        data = {"body": message}
        response = requests.post(url, headers=headers, json=data, verify=False)
        logger.debug(
            f"Add comment to commit {last_commit_id}: {response.status_code}, {response.text}"
        )
        if response.status_code == 201:
            logger.info("Comment successfully added to push commit.")
        else:
            logger.error(f"Failed to add comment: {response.status_code}")
            logger.error(response.text)

    def repository_compare(self, before: str, after: str):
        url = f"{self.gitea_url}/api/v1/repos/{self.repo_owner}/{self.repo_name}/compare/{before}...{after}"
        headers = {"Authorization": f"token {self.gitea_token}"}
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Get compare from Gitea: {response.status_code}, {response.text}")

        if response.status_code == 200:
            files = response.json().get("files", [])
            changes = []
            for file in files:
                changes.append(
                    {
                        "old_path": file.get("filename"),
                        "new_path": file.get("filename"),
                        "diff": file.get("patch", ""),
                    }
                )
            return changes
        else:
            logger.warn(
                f"Failed to get compare: {response.status_code}, {response.text}"
            )
            return []

    def get_push_changes(self) -> list:
        if not self.commit_list:
            logger.info("No commits found in push event.")
            return []

        before = self.webhook_data.get("before", "")
        after = self.webhook_data.get("after", "")

        if before and after:
            if after.startswith("0000000"):
                return []
            if before.startswith("0000000"):
                before = f"{after}^"
            return self.repository_compare(before, after)
        else:
            return []
