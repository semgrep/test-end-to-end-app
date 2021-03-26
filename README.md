# test-end-to-end-app

## Motivation

This repository exists for the sole purpose of testing whether Semgrep CI (semgrep-app and semgrep-action) is working smoothly end-to-end. 
Unlike our internal dogfooding efforts, this repo runs tests at a regular, scheduled cadence and intentionally includes Semgrep-recognized code bugs, to verify that Semgrep's recall in particular is 100%.

We use this repo:
1. To collect data about how frequently Semgrep CI fails (downtime)
2. To notify on-call engineers within 20 minutes of a new bug being introduced to staging
3. To notify on-call engineers within 20 minutes of a new bug being introduced to production

## How it works

### The basics

Every 20 minutes, a GitHub Actions job is triggered that runs the script `test-semgrep-app-e2e.py`
This script opens a new pull request (using Clara's personal access token) that introduces a vulnerability into this code base
This triggers two more GitHub Actions jobs, one on semgrep-staging and another on semgrep-prod (these jobs run `on: pull_request`)
Staging is configured to find a useless-eqeq bug, post a PR comment inline, and send a slack notification to the #e2e-tests slack channel
Prod is configured to find a hardcoded-token bug, post a PR comment inline, and send a slack notification to the #e2e-tests slack channel
The script that opened the new pull request then starts occasionally checking Slack and GitHub (using api calls) to check whether the existed notifications have been posted.
If all expected notifications are present, the script closes the pull request and returns 0, passing the e2e-test
If any expected notifications are missing, the script leaves the pull request open (for debugging purposes), returns 1, and fails the e2e-test

### Robustifying

Every time the end-to-end test runs and succeeds, it sends an INFO-level notification to Sentry. Sentry is configured to alert on-call channels if the number of these INFO-level notifications ever drops below 1 over a 2-hour window. This happens if 
1. GitHub actions is down
2. The end-to-end test begins to fail regularly
3. Someone accidentally tweaks this repo and the end-to-end test stops running altogether

## What to do if you are on call, and the end-to-end test fails

First check the open pull requests, and examine which ones are open. The pull requests whose tests succeed get closed, so the ones you need to examine should be right at the top. 

Look for two PR comments, one from staging and one from prod. Look also for GitHub Actions tests that ran. There should be one for staging and one for prod, both of which should have finished and failed the build. 

Finally, check on the #e2e-tests slack channel and look for 2 notifications corresponding to each PR that was opened. Based on what is missing (PR comments or slack notifications for staging or prod) you should be able to narrow down what part of the app is not functioning properly.
