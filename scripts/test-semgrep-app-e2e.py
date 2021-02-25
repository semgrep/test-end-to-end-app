import requests
import base64
import time, sys, os
from typing import Optional
from typing import Dict
from typing import Any
from http import HTTPStatus
import sentry_sdk

##############################################################################
######## CONSTANTS ###########################################################
##############################################################################

REPO = "semgrep/test-end-to-end-app"
TEST_FILE_PATH = "test.py"

BASE_REF = "main"
GH_ACCEPTS_HEADER = "application/vnd.github.v3+json"
GH_TOKEN = os.getenv("GITHUB_TOKEN", "")
GH_HEADERS = {"Authorization": f"Bearer {GH_TOKEN}", "Accept": GH_ACCEPTS_HEADER}

SLACK_TOKEN = os.getenv("SLACK_E2E_TOKEN", "") 
SLACK_CHANNEL = "C01P3ML7F41"

SENTRY_DSN = os.getenv("SENTRY_DSN", "")

##############################################################################
######## GITHUB API CALLS ####################################################
##############################################################################

def gh_create_branch(branch: str) -> None:
    resp = requests.get(
        f"https://api.github.com/repos/{REPO}/git/refs/heads/{BASE_REF}",
        headers=GH_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    default_branch_info = resp.json()
    create_branch_url = f"https://api.github.com/repos/{REPO}/git/refs"
    head_ref = f"refs/heads/{branch}"
    body = {"ref": head_ref, "sha": default_branch_info.get("object", {}).get("sha")}
    resp = requests.post(create_branch_url, headers=GH_HEADERS, json=body, timeout=30)
    if (
        resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        and resp.json()["message"] == "Reference already exists"
    ):
        raise Exception(f"Repo {repo_full_name} already has a branch named {branch}")
    resp.raise_for_status()

def gh_create_file(
    file_path: str,
    file_contents: str,
    branch: Optional[str] = None,
) -> str:
    url = f"https://api.github.com/repos/{REPO}/contents/{file_path}"
    body = {
        "message": f"add {file_path}",
        "committer": {"name": "semgrep.dev", "email": "support@r2c.dev"},
        "content": base64.b64encode(file_contents.encode()).decode(),
    }
    params = {}
    if branch is not None:
        body["branch"] = branch
        params["ref"] = branch

    # first we try to do a GET to get the sha
    resp = requests.get(url, headers=GH_HEADERS, params=params, timeout=30)
    if resp.status_code == requests.codes.ok:
        body["sha"] = resp.json().get("sha")

    resp = requests.put(url, headers=GH_HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    html_url = data.get("content", {}).get("html_url")
    return html_url

def gh_create_pr(
    pr_body: Dict[str, Any],
    base_ref: str,
    branch: str,
) -> str:
    url = f"https://api.github.com/repos/{REPO}/pulls"
    body = {
        "head": branch,
        "base": base_ref,
        "maintainer_can_modify": True,
        **pr_body,
    }
    resp = requests.post(url, headers=GH_HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    pr_id = data.get("number")
    return pr_id

def gh_get_reviews(
    pull_number: int,
):
    url = f"https://api.github.com/repos/{REPO}/pulls/{pull_number}/reviews"
    resp = requests.get(url, headers=GH_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data

def gh_get_review_comments(
    pull_number: int,
    review_id: int,
):
    url = f"https://api.github.com/repos/{REPO}/pulls/{pull_number}/reviews/{review_id}/comments"
    resp = requests.get(url, headers=GH_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data

def gh_close_pr(
    pull_number: int,
):
    url = f"https://api.github.com/repos/{REPO}/pulls/{pull_number}"
    body = {
        "state": "closed"
    }
    resp = requests.patch(url, headers=GH_HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    assert(data.get('closed_at') != None)

def gh_delete_branch(
    branch: str
):
    head_ref = f"heads/{branch}"
    url = f"https://api.github.com/repos/{REPO}/git/refs/{head_ref}"
    resp = requests.delete(url, headers=GH_HEADERS, timeout=30)

##############################################################################
######### SLACK API CALLS ####################################################
##############################################################################

def slack_last_message():
    url = f"https://slack.com/api/conversations.history?channel={SLACK_CHANNEL}&limit=1"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    msgs = data.get('messages')
    if msgs:
        return msgs[0]
    return False

##############################################################################
######### SENTRY API CALLS ###################################################
##############################################################################

def notify_sentry(message: str, level: str):
    sentry_sdk.init(
        SENTRY_DSN,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0,
        environment="prod",
    )
    sentry_sdk.set_level(level)
    sentry_sdk.capture_message(message)

##############################################################################
######## HELPER FUNCTIONS ####################################################
##############################################################################

def get_run_id() -> int:
    return int(time.time())

def get_branch_from_id(run_id: int) -> str:
    return f"testing-{run_id}"

def create_branch(run_id: int) -> str:
    branch_name = get_branch_from_id(run_id)
    gh_create_branch(branch=branch_name)
    return branch_name

def update_file(run_id: int) -> None:
    file_contents = f"""import random
print({run_id})

if {run_id} == {run_id}:
    print("got here")

client("s3", aws_secret_access_key="fakefakefake{run_id}fakefake")
"""
    gh_create_file(TEST_FILE_PATH, file_contents=file_contents, branch=get_branch_from_id(run_id))

def open_pr(run_id: int) -> str:
    return gh_create_pr({"title": f"Test run: {run_id}", "body": f"Test PR for test run_id: {run_id}"}, BASE_REF, branch=get_branch_from_id(run_id))

def validate_pr_comment(pull_number: int):
    reviews = gh_get_reviews(pull_number)
    if len(reviews) < 1:
        # PR comment has not yet been posted
        return False
    review_id = reviews[0].get('id')
    comments = gh_get_review_comments(pull_number, review_id)
    if len(comments) < 1:
        return False
    if comments[0].get('path') != 'test.py':
        return False
    if 'useless-eqeq' not in comments[0].get('body'):
        return False
    return True

def validate_slack_notification(run_id: int):
    message = slack_last_message()
    return (REPO in message.get('text','')) and (str(run_id) in message['blocks'][1]['elements'][1]['text'])


def close_pr(pull_number: int):
    gh_close_pr(pull_number)

##############################################################################
###### MAIN ##################################################################
##############################################################################

def run_tests():
    run_id = get_run_id()

    # Create a new PR with a known eqeq bug
    new_branch = create_branch(run_id)
    update_file(run_id)
    pr_id = open_pr(run_id)

    message = None
    for i in range(3):
        # wait for Semgrep to finish running on the PR
        time.sleep(50)
        pr_comments = validate_pr_comment(pr_id)
        message = validate_slack_notification(run_id)
        if pr_comments and message:
            break
        if i < 2:
            print('Missing at least one notification... checking again in a minute')

    close_pr(pr_id)
    gh_delete_branch(get_branch_from_id(run_id))
    if pr_comments and message:
        print("SUCCESS!")
        notify_sentry("testing e2e test alarm system - ignore me", "info")
        sys.exit(0)
    
    # all other cases
    print("TEST FAILED")
    notify_sentry("End-to-end Semgrep test failed on semgrep.dev", "error")
    sys.exit(1)


if __name__ == "__main__":
    run_tests()