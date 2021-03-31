# CONTRIBUTING

This repo does not use any particularly fancy frameworks. All you need is access to this "semgrep" org on GitHub (and therefore on semgrep.dev) and python.

To change how frequently this test runs, edit `.github/workflows/test-semgrep.yml`
To change the contents of the pull request that is opened, edit `./scripts/test-semgrep-app-e2e.py`
To change the policy that will run, go to the Semgrep Dashboard on semgrep.dev or staging.semgrep.dev

To test your changes locally, you can just run `python ./scripts/test-semgrep-app-e2e.py`. You will need to set some environment variables (`export MY_ENV_VARIABLE=value`) locally to make this work:
- `GITHUB_TOKEN`: Use a Personal Access Token (PAT) with "repo" level permissions; you can create one of these for yourself on GitHub, [here](https://github.com/settings/tokens).
- `SLACK_E2E_TOKEN`: This is stored in 1password. It is the "User OAuth Token" associated with a Slack
  app called "Test-e2e", which has only the required permissions (to view r2c Slack channels).
- `SENTRY_DSN`: This is stored in 1password, and also viewable on the Semgrep [Sentry page](https://sentry.io/settings/r2c/projects/semgrep/keys/)

You can also test the action job by navigating to the "Actions" tab in GitHub, selecting "Test Semgrep CI End to End", and clicking "Run workflow" with your own branch selected.

**Note: The cron job will not run exactly every X minutes, but is subject to availability of GitHub Actions.**
When configured to run every 20 minutes, it actually runs around 1-3 times per hour, and occasionally fails to run at all in a given hour.
