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
      - name: Compute lowercase image name
        id: image
        run: |
          echo "repo=$(echo '${{ github.repository }}' | tr '[:upper:]' '[:lower:]')" >> "$GITHUB_OUTPUT"

      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ steps.image.outputs.repo }}:${{ github.sha }}
            ghcr.io/${{ steps.image.outputs.repo }}:latest
```
This *is* `docker build` + `docker push` — the same Dockerfile from the
Docker lesson — just running on GitHub's machine instead of yours. Two
tags: one pinned to the exact commit (`github.sha`, immutable) and a
floating `latest` (always means "whatever was pushed most recently").

**Real failure hit on the actual first run**: `github.repository` preserves
the account's real casing (`LakshyaTecno/resume-screening-service`), but
Docker image names must be all-lowercase — `docker/build-push-action`
rejected it outright with `repository name must be lowercase`. Fixed by
adding a step that lowercases it with `tr` and referencing that output
instead. Small, but a genuinely common gotcha with GHCR specifically (an
org/user with any uppercase letters in its name hits this immediately).

## The deliberate stopping point

This workflow never touches a cluster. It never runs `kubectl` or `helm
install`. Deploying is a separate concern, handled by ArgoCD
(`argocd/application.yaml`), which watches this repo's Helm chart and pulls
changes rather than CI pushing them. That split is what "GitOps" actually
means.

## Closing the loop: the image-tag bridge

For a while, this workflow genuinely stopped right after "image pushed" —
and that was a real bug, not a design choice. ArgoCD only watches **git**,
never the registry. Pushing a new image tagged `latest` doesn't give
ArgoCD anything to react to, because nothing in git changed. A hundred new
images could get pushed under that same floating tag and ArgoCD would sit
there reporting `Synced`, unaware anything happened.

The fix, added as the very last step of `build-and-push`:

```yaml
      - name: Update Helm chart image tag
        run: |
          sed -i "s|repository: .*|repository: ghcr.io/${{ steps.image.outputs.repo }}|" charts/resume-screening-service/values.yaml
          sed -i "s|tag: .*|tag: \"${{ github.sha }}\"|" charts/resume-screening-service/values.yaml
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add charts/resume-screening-service/values.yaml
          git diff --staged --quiet || git commit -m "chore: bump image tag to ${{ github.sha }} [skip ci]"
          git push
```

CI writes the new tag directly into `values.yaml` and pushes that commit
back to `main` itself. *Now* there's a real git change — and that's the
whole trick, since ArgoCD's entire job is reacting to exactly that.

**The one thing that would silently break this**: that commit lands on
`main`, which is exactly what triggers this workflow in the first place
(`on: push: branches: [main]`). Without a guard, every deploy would
trigger a new CI run that deploys itself, forever. `[skip ci]` in the
commit message is load-bearing — GitHub Actions recognizes that exact
marker and won't start a new run for a commit containing it.

`git diff --staged --quiet || git commit ...` is the other small but
necessary piece: without it, re-running this job against a commit whose
tag was already written would hit "nothing to commit" and fail the step
outright.

**Permissions**: `build-and-push` gets its own job-level `permissions:
{ contents: write, packages: write }`, separate from the workflow's
top-level `contents: read`. Job-level permissions *replace* the top-level
block for that job rather than adding to it — `lint-and-test` never gets
write access to the repo, only the one job that actually needs to push a
commit does.

**A real mistake, on the very first attempt to verify this**: the commit
that introduced this whole fix *explained* the skip-ci marker in its own
message — in English, describing what the marker does. GitHub Actions
doesn't parse intent; it just checks whether that exact bracketed text
appears anywhere in the commit message. Explaining the mechanism was
enough to trigger it. That commit silently skipped its own CI run, so the
change that added CI verification shipped with zero verification the
first time around. Lesson: never write that literal marker text in a
commit message unless you actually mean to skip that commit specifically
— including inside an explanation of what it does.
