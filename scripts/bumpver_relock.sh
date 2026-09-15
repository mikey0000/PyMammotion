#!/usr/bin/env bash
# Runs from bumpver's pre_commit_hook: after it patches the version files, before
# it commits them.
#
# uv.lock records the workspace version, so it has to move with the bump and land
# in the same commit -- CI runs `uv sync --frozen` against the release tag. It also
# has to be consistent *before* git commit, because the ty and pytest pre-commit
# hooks shell out to `uv run`, which re-resolves on a version change and rewrites
# uv.lock mid-commit. pre-commit then aborts with "files were modified by this
# hook" and bumpver's commit fails, leaving the bump staged but uncommitted.
set -euo pipefail

uv lock
git add uv.lock
