#!/bin/bash
# shellcheck disable=SC2154
#
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PR_NUMBER=$(jq -r ".pull_request.number" $GITHUB_EVENT_PATH)
STATUSES_URL=$(jq -r ".pull_request.statuses_url" $GITHUB_EVENT_PATH)

if [ "$STATUSES_URL" == "" ]; then
  # Do not run link checks when this isn't a test build. Have to mark it as successful as there isn't
  # a GitHub status of skipped.
  echo "Skipping link checks"
  touch "$GITHUB_WORKSPACE/../linktests-success"
  exit 0
fi

# Note: do NOT use "set -e" in this script because we need the "if" statement to execute and it won't
# if we use "set -e"

# If we're running a test, the built site gets moved outside of the working direcory
if [ "$STATUSES_URL" == "" ]; then
  BUILDDIR="$GITHUB_WORKSPACE/$SITE_URL"
else
  BUILDDIR="/srv/websitepreview/$AWS_STATIC_SITE_URL-$PR_NUMBER"
fi

if ! "$DIR/check-links-3.py" -d "$BUILDDIR" -o "$GITHUB_WORKSPACE/../linktests-output" "$@"
then
  # If we *aren't* running a test build, output the results so that it is in the Bamboo log.
  if [ "$STATUSES_URL" == "" ]; then
    echo ""
    cat "$GITHUB_WORKSPACE/../linktests-output"
  fi
  touch "$GITHUB_WORKSPACE/../linktests-fail"
  exit 1
else
  touch "$GITHUB_WORKSPACE/../linktests-success"
  exit 0
fi
