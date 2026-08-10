# CI (GitHub Actions), explained

Notes on `.github/workflows/ci.yml`. This file has **never actually run** —
this repo has no GitHub remote yet, only a local `git init`. Everything
below is what the file *will* do once pushed, verified by reading it
carefully, not by watching it execute.

## The big picture: two separate jobs, not one linear sequence

```
Pull request opened/updated ──▶ Job 1: lint-and-test ──▶ stops (no image)

Push to main (e.g. a merge)  ──▶ Job 1: lint-and-test ──▶ Job 2: build-and-push
                                                            (docker build + push
                                                             to ghcr.io)
```

A pull request only ever triggers **Job 1** — checkout, install Python,
install dependencies, run `black`/`isort`/`pytest`. Nothing gets built,
no matter how many commits get pushed to that PR branch. That's valuable
by itself: you get pass/fail feedback *during code review*, before anything
merges.

A merge is really just GitHub pushing a new commit onto `main`. *That* push
triggers Job 1 again, and — only if it passes, and only because this run's
trigger was a push to `main` specifically — Job 2 runs: builds the Docker
image and pushes it to GHCR.

**No database is involved anywhere in this file.** Docker isn't "installed"
either — GitHub's runner machines come with it pre-installed; the workflow
just uses it (`docker/login-action`, `docker/build-push-action`).

## `on:` — the trigger

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```
Run this workflow on a push to `main`, or on a PR targeting `main`.

## `permissions:`

```yaml
permissions:
  contents: read
  packages: write
```
GitHub Actions runs with minimal permissions by default. `contents: read`
lets it clone the repo; `packages: write` lets it push to GHCR later
(GitHub calls container images "packages").

## Job 1: `lint-and-test`

```yaml
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
```
Each job gets a **fresh, temporary Linux virtual machine** — not your Mac,
thrown away after the run. `actions/checkout@v4` is a reusable step that
clones the repo onto that empty machine; without it there'd be no code
there at all.

```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: black --check .
      - run: isort --check-only .
      - run: pytest || [ $? -eq 5 ]
```
Installs Python 3.11 (yet another separate Python 3.11 — unrelated to your
Mac's, unrelated to the one baked into the Docker image), installs the
project + dev deps, then runs the exact same `black`/`isort` checks that
were run by hand earlier on `app/worker.py`/`app/config.py`, plus `pytest`.
The `|| [ $? -eq 5 ]` treats pytest's "found zero tests" exit code as
acceptable for now (true until a `tests/` folder exists) while still
failing loudly on any real test failure.

## Job 2: `build-and-push`

```yaml
  build-and-push:
    needs: lint-and-test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
```
`needs` makes this job wait for Job 1 to *succeed* first — a broken build
never gets an image. The `if` is the PR-vs-push gate described above.

```yaml
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
```
`secrets.GITHUB_TOKEN` is a temporary credential GitHub generates
automatically for every workflow run — no manual secret setup needed for
this particular registry (a real external one, like a private AWS ECR,
would need real credentials configured as repo secrets).

```yaml
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.sha }}
            ghcr.io/${{ github.repository }}:latest
```
This *is* `docker build` + `docker push` — the same Dockerfile from the
Docker lesson — just running on GitHub's machine instead of yours. Two
tags: one pinned to the exact commit (`github.sha`, immutable) and a
floating `latest` (always means "whatever was pushed most recently").

## The deliberate stopping point

This workflow never touches a cluster. It stops the moment the image exists
in GHCR. That boundary is intentional — deploying it is a separate concern,
handled by ArgoCD (`argocd/application.yaml`), which watches this repo's
Helm chart and pulls changes rather than CI pushing them. That split is
what "GitOps" actually means, and it's the next topic.
