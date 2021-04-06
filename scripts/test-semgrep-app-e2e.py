import requests
import base64
import time, sys, os
import logging
from typing import Optional
from typing import Dict
from typing import Any
from http import HTTPStatus
import sentry_sdk

logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', level=logging.INFO)
logger = logging.getLogger(__file__)

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


def gh_get_status() -> bool:
    GH_STATUS_ENDPOINT = "https://kctbh9vrtdwd.statuspage.io/api/v2/components.json"
    try:
        resp = requests.get(GH_STATUS_ENDPOINT, timeout=5)
        resp.raise_for_status()
        gha = next(filter(lambda component: component["id"] == "br0l2tvcx85d", resp.json()["components"]))
        if gha["status"] != "operational":
            return False
        logging.info("GitHub Actions are currently operational")
        return True
    except Exception:
        # Assume GH Actions is working if status is down; we'd rather fail the entire e2e test loudly than silently
        # do nothing here
        logging.exception(f"Could not read GHA status from {GH_STATUS_ENDPOINT}")
        return True


def gh_get_check_run_started(branch: str) -> bool:
    action_endpoint = f"https://api.github.com/repos/{REPO}/commits/{branch}/check-runs"
    attempts_remaining = 10
    sleep_seconds = 12.0
    while attempts_remaining:
        attempts_remaining -= 1
        logging.info(f"Checking for start of semgrep-action run... (approximately {attempts_remaining * sleep_seconds / 60.0} minutes remaining)")
        try:
            resp = requests.get(action_endpoint, timeout=5)
            resp.raise_for_status()
            run_counts = resp.json()["total_count"]
            if run_counts >= 2:  # We run a prod and a staging action
                logging.info("Semgrep-action checks have started")
                return True
        except Exception:
            logging.exception(f"Could not read check runs from {action_endpoint}")
        time.sleep(sleep_seconds)
    return False


def gh_create_branch(branch: str) -> None:
    logging.info(f"Creating branch {branch}")
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
        raise Exception(f"Repo {REPO} already has a branch named {branch}")
    resp.raise_for_status()

def gh_create_file(
    file_path: str,
    file_contents: str,
    branch: Optional[str] = None,
) -> str:
    logging.info(f"Creating file {file_path} on branch {branch}")
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
    logging.info(f"Creating PR with body {pr_body} on branch {branch} against {base_ref}")
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
    logging.info(f"Getting reviews for PR ID {pull_number}")
    url = f"https://api.github.com/repos/{REPO}/pulls/{pull_number}/reviews"
    resp = requests.get(url, headers=GH_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data

def gh_get_review_comments(
    pull_number: int,
    review_id: int,
):
    logging.info(f"Getting review comments for PR ID {pull_number}")
    url = f"https://api.github.com/repos/{REPO}/pulls/{pull_number}/reviews/{review_id}/comments"
    resp = requests.get(url, headers=GH_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data

def gh_close_pr(
    pull_number: int,
):
    logging.info(f"Closing PR with number {pull_number}")
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
    logging.info(f"Deleting branch {branch}")
    head_ref = f"heads/{branch}"
    url = f"https://api.github.com/repos/{REPO}/git/refs/{head_ref}"
    resp = requests.delete(url, headers=GH_HEADERS, timeout=30)

##############################################################################
######### SLACK API CALLS ####################################################
##############################################################################

def slack_last_x_messages(num_messages: int):
    logging.info(f"Retrieving the last {num_messages} messages from Slack channels {SLACK_CHANNEL}")
    if not SLACK_TOKEN:
        raise Exception("No SLACK_E2E_TOKEN set")
    url = f"https://slack.com/api/conversations.history?channel={SLACK_CHANNEL}&limit={num_messages}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    msgs = data.get('messages')
    return msgs

##############################################################################
######### SENTRY API CALLS ###################################################
##############################################################################

def notify_sentry(message: str, pr_id: int, level: str):
    logging.info(f"Posting to Sentry: {message}")
    sentry_sdk.init(
        SENTRY_DSN,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0,
        environment="prod",
    )
    sentry_sdk.set_level(level)

    pr_url = f"https://github.com/semgrep/test-end-to-end-app/pull/{pr_id}"

    with sentry_sdk.push_scope() as scope:
        scope.set_extra("pr_id", pr_id)
        scope.set_extra("pr_url", pr_url)
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

def validate_pr_comment(pull_number: int, rule: str):
    reviews = gh_get_reviews(pull_number)
    if len(reviews) > 2:
        logging.error("Overrides may have stopped working")
        notify_sentry("End-to-end Semgrep test for overrides failed", "error")
        sys.exit(1)
    review_ids = [reviews[i].get('id') for i in range(len(reviews))]
    for review_id in review_ids:
        comments = gh_get_review_comments(pull_number, review_id)
        if len(comments) >= 1 and rule in comments[0].get('body'):
            return True
    return False

def validate_slack_notifications(run_id: int):
    messages = slack_last_x_messages(2)
    if len(messages) < 2:
        logging.error('found fewer than 2 slack messages')
        return False
    for message in messages:
        if (str(run_id) not in message['blocks'][1]['elements'][1]['text']):
            return False
    return True

def close_pr(pull_number: int):
    gh_close_pr(pull_number)

##############################################################################
###### MAIN ##################################################################
##############################################################################

def run_tests():
    run_id = get_run_id()

    if not gh_get_status():
        logging.error("GitHub actions is currently down; returning with success code to avoid false positives")
        sys.exit(0)

    # Create a new PR with a known eqeq bug
    new_branch = create_branch(run_id)
    update_file(run_id)
    pr_id = int(open_pr(run_id))

    if not gh_get_check_run_started(new_branch):
        logging.error("GitHub actions are not starting; returning with success code to avoid false positives")
        sys.exit(0)

    pr_comment_prod, pr_comment_staging, slack_notifications = False, False, False

    for i in range(8):
        # wait for semgrep and staging.semgrep to finish running on the PR
        logging.info(f"Sleeping for 2 minutes...")
        time.sleep(120)
        pr_comment_staging = validate_pr_comment(pr_id, 'useless-eqeq')
        pr_comment_prod = validate_pr_comment(pr_id, 'hardcoded-token')
        slack_notifications = validate_slack_notifications(run_id)
        if pr_comment_staging and pr_comment_prod and slack_notifications:
            break
        # Gives reassurance that action is still looking
        if i < 3:
            logging.warning('Missing at least one notification... checking again in two minutes')

    if pr_comment_prod and not pr_comment_staging:
        logging.error("TEST FAILED ON STAGING")
        notify_sentry(f"End-to-end Semgrep test failed on staging.semgrep.dev: no PR comment", pr_id, "error")
        sys.exit(1)
            
    if pr_comment_staging and pr_comment_prod and slack_notifications:
        close_pr(pr_id)
        gh_delete_branch(get_branch_from_id(run_id))
        logging.info("SUCCESS!")
        notify_sentry("testing e2e test alarm system - ignore me", pr_id, "info")
        sys.exit(0)
    
    # all other cases
    logging.error("TEST FAILED")
    prod_failure_mode = "no PR comment" if not pr_comment_prod else "no Slack notification"
    notify_sentry(f"End-to-end Semgrep test failed on semgrep.dev: {prod_failure_mode}", pr_id, "error")
    sys.exit(1)


if __name__ == "__main__":
    run_tests()
