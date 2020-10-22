#!/bin/bash
# shellcheck disable=SC2154
#
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PR_NUMBER=$(jq -r ".pull_request.number" $GITHUB_EVENT_PATH)
STATUSES_URL=$(jq -r ".pull_request.statuses_url // empty" $GITHUB_EVENT_PATH)

if [ -z "$STATUSES_URL" ]; then
  # If we're not running a test, the built site is likely to be in the cache
  # directory so we get passed the path on the command line.
  BUILDDIR="$1"
else
  # If we're running a test, the built site gets moved outside of the working direcory
  BUILDDIR="/srv/websitepreview/$AWS_STATIC_SITE_URL-$PR_NUMBER"
fi

cd $DIR
pipenv run python check-links-3.py -d "$BUILDDIR" "$@"
