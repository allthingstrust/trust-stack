# Creating Pull Requests in this environment

The provided automation (`make_pr` tool) expects a clean, committed branch **before** a PR can be opened. Calling `make_pr` without a new commit (or with untracked changes only) results in a `failed to create PR` error.

> Note: "run tests locally" means running them in this workspace (the hosted container where you are editing the code). The `make_pr` helper does **not** automatically execute tests, so you should run the relevant commands yourself (for example, `pytest ...`) before committing. If you only changed documentation, you can skip tests.

Follow this flow to avoid the error:

1. Make your code changes.
2. Run tests in the current workspace as needed.
3. Stage and commit your changes (`git commit ...`).
4. Ensure `git status` is clean.
5. Invoke the `make_pr` tool with the PR title and description.

If the branch has no new commits since the last PR attempt, create a new commit (even a small documentation update) before retrying `make_pr`.
