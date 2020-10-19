#!/bin/bash
# shellcheck disable=SC2154
set -e
cd "$GITHUB_WORKSPACE" || exit 1
INCOMING_OWNER=$(jq ".pull_request.head.repo.owner.login" $GITHUB_EVENT_PATH)
INCOMING_BRANCH=$(jq ".pull_request.head.ref" $GITHUB_EVENT_PATH)
INCOMING_REPO=$(jq ".pull_request.head.repo.clone_url" $GITHUB_EVENT_PATH)

echo "git checkout -b $INCOMING_OWNER-$INCOMING_BRANCH $GITHUB_BASE_REF"
git checkout -b "$INCOMING_OWNER-$INCOMING_BRANCH" "$GITHUB_BASE_REF"
echo "git pull $INCOMING_REPO $INCOMING_BRANCH"
git pull "$INCOMING_REPO" "$INCOMING_BRANCH"
