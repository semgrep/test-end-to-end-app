# CONTRIBUTING

This repo does not use any particularly fancy frameworks. All you need is access to this "semgrep" org on GitHub (and therefore on Semgrep.dev) and python.

To change how frequently this test runs, edit `.github/workflows/test-semgrep.yml`
To change the contents of the pull request that is opened, edit `./scripts/test-semgrep-app-e2e.py`
To change the policy that will run, go to the Semgrep Dashboard on semgrep.dev or staging.semgrep.dev

To test your changes locally, you can just run `python ./scripts/test-semgrep-app-e2e.py`
You can also test the action job by navigating to the "Actions" tab in GitHub, selecting "Test Semgrep CI End to End", and clicking "Run workflow"

**Note: The cron job will not run exactly every X minutes, but is subject to availability of GitHub Actions.**
When configured to run every 20 minutes, it actually runs around 1-3 times per hour, and occasionally fails to run at all in a given hour.
