# Reproducing GitHub Actions + Branch Protection (copyable guide)

This document shows how to reproduce the GitHub Actions + branch-protection setup we use in this repository in another project. It includes:

- Two example workflows (PR lint + CI)
- How to avoid noisy legacy errors (temporary ignores)
- Branch protection JSON and `gh` command to apply it
- Quick verification and operational notes

Use this as a template — adapt `--exclude` and `--ignore` flags to your repo.

## 1) Create workflow folder

Create the folder `.github/workflows/` at the repository root (if not present).

## 2) Add PR-linter workflow

Create file `.github/workflows/pr-review.yml` with the following content (copy & paste):

```yaml
name: Python PR Review

on:
  pull_request:
    branches: [ main ]

jobs:
  lint-and-test:
    name: lint-and-test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install flake8
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
      - name: Run Linter
        run: |
          # Tune --exclude and --extend-ignore for your repo
          flake8 . --exclude=archive,.venv --count --select=E9,F63,F7 \
            --extend-ignore=F821,F823,F824 --show-source --statistics
```

Notes:
- `--select=E9,F63,F7` makes flake8 only fail on the most serious issues (syntax, fatal errors). Adjust as you want.
- `--extend-ignore=F821,F823,F824` were used in our repo temporarily to avoid failing on many legacy undefined-names. Don't keep these ignores forever — prefer to fix the code.
- Adjust `--exclude` to ignore local build artifacts, model data, or virtualenvs that exist in your repo.

## 3) Add CI workflow (tests + linters)

Create file `.github/workflows/ci.yml` with the following content:

```yaml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
      - name: Run tests
        run: |
          # If you have broken legacy tests, temporarily ignore them with --ignore
          PYTHONPATH=. pytest -q
```

If your test suite includes legacy tests that fail at collection time, add `--ignore=tests/test_legacy.py` or similar to the pytest command while you fix them.

## 4) Optional: disable or scope noisy checks

If your repo contains large legacy code, test fixtures, or documentation templates that cause linters to fail (common in large projects), you can temporarily:

- Add `--extend-ignore=F821` to flake8 to ignore undefined names (but track this as tech debt)
- Use `flake8 --exclude=dir1,dir2` to skip directories
- Use `pytest --ignore=tests/test_old.py` to skip old tests

These are temporary measures — plan a cleanup task to remove ignores later.

## 5) Branch protection (require checks before merge)

Create a JSON file `branch_protection.json` with the desired policy (example below). This makes GitHub require passing checks before allowing a merge into `main`.

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["lint-and-test"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0
  },
  "restrictions": null
}
```

Then run (with `gh` CLI) to apply it (replace OWNER/REPO with your repo):

```bash
gh api -X PUT /repos/OWNER/REPO/branches/main/protection --input branch_protection.json
```

Notes:
- `contexts` must match the check names shown in the Actions UI. If your workflow job name is `lint-and-test`, that typically appears as `lint-and-test` in contexts.
- Set `required_approving_review_count` to the minimum number of human approvals (0 to bypass review requirement).

## 6) Create PR and validate

1. Create a branch and push your workflows:

```bash
git checkout -b chore/add-ci
git add .github/workflows/pr-review.yml .github/workflows/ci.yml
git commit -m "chore(ci): add GitHub Actions workflows"
git push -u origin chore/add-ci
```

2. Open a PR (you can use `gh`):

```bash
gh pr create --title "chore(ci): add workflows" --body "Adds PR lint and CI workflows."
```

3. Confirm checks run in the Pull Request and, if one is failing due to legacy issues, either update workflows to temporarily ignore them or fix the offending code.

## 7) Triage modal: common failing reasons and quick fixes

- SyntaxError in a file => fix code (flake8 E9 will catch this).
- F821 undefined name across many files => either add missing imports / variables, or temporarily `--extend-ignore=F821`.
- Tests failing at import collection => tests import modules that no longer exist. If they are legacy tests, use `--ignore` for them; otherwise update tests.
- Markdown lint failing on templates => either fix the template files or remove/disable docs CI while migrating docs.

## 8) Recommended follow-ups

- Remove temporary ignores and exclusions after you fix the underlying problems.
- Add `mypy` or `pytest --maxfail=1 --disable-warnings` jobs if desired.
- Add badges to README to show CI status.

## 9) Example: quick apply script

This small script shows how you could programmatically add branch protection after pushing workflows (requires `gh`):

```bash
# Create branch_protection.json (see earlier) then:
gh api -X PUT /repos/OWNER/REPO/branches/main/protection --input branch_protection.json
```

---

If you want, I can:

- Produce ready-to-copy YAML files adapted to a target repo (tell me owner/repo and directories to ignore), or
- Open a PR in another repo (if you give me the repo and `gh` access) and apply these changes directly.

