#!/usr/bin/env bash
# Runs from bumpver's post_commit_hook, which fires after the bump commit.
#
# bumpver tags with the bare version (vcs.py: tag_name=new_version) and has no
# setting for a prefix, but release.yml triggers on 'v*' -- so a bumpver-made tag
# never starts a release. bumpver's own tagging is off (tag = false); this makes
# the v-prefixed one instead.
set -euo pipefail

: "${BUMPVER_NEW_VERSION:?bumpver did not export BUMPVER_NEW_VERSION}"
git tag "v${BUMPVER_NEW_VERSION}"
echo "tagged v${BUMPVER_NEW_VERSION}"
