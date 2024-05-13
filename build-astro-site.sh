#!/bin/bash
# shellcheck disable=SC2154
#
# Note: do NOT use "set -e" in this script because we need the "if" statement to execute and it won't
# if we use "set -e"

function setup_vars(){
    PR_NUMBER=$(jq -r ".pull_request.number" $GITHUB_EVENT_PATH)
    STATUSES_URL=$(jq -r ".pull_request.statuses_url // empty" $GITHUB_EVENT_PATH)
}

function setup_testing(){
  if [ ! -z "$STATUSES_URL" ]; then
    echo "Setting up for testing"
    # What is the URL going to be for this site?
    BUILDDIR="$AWS_STATIC_SITE_URL-$PR_NUMBER"
    URL="http://$BUILDDIR.ghactions.linaro.org"
  fi
}

function build_site(){
  yarn install
  if [ -d "dist" ]; then rm -Rf dist; fi
  yarn build
}

function post_build_cleanup(){
  if [ ! -z "$STATUSES_URL" ]; then
    echo "post_build_cleanup"
    # If we already have a preview directory with this name, we need to remove
    # it first.
    if [ -d "/srv/websitepreview/$BUILDDIR" ]; then
      rm -r /srv/websitepreview/"$BUILDDIR"
    fi
  fi
}

function post_build_deploy_preview(){
  if [ ! -z "$STATUSES_URL" ]; then
    echo "post_build_deploy_preview"
    # Change group so that www-data can read the site for previews. We do this
    # rather than owner so that the owner (ubuntu) continues to have rw perms
    # which is important when cleaning up.
    sudo chgrp -R www-data dist
    # Move the built directory into the preview space
    mv dist /srv/websitepreview/"$BUILDDIR"
    # Send the status update to GitHub for the preview URL
    DATA="{\"state\": \"success\", \"target_url\": \"$URL\", \"context\": \"Deploy preview\", \"description\": \"Deployment complete\"}"
    curl -s -S -H "Content-Type: application/json" -H "Authorization: token $TOKEN" -d "$DATA" "$STATUSES_URL" >/dev/null
  fi
}

function post_build_failed_preview(){
  if [ ! -z "$STATUSES_URL" ]; then
    echo "post_build_failed_preview"
    # Send the status update to GitHub to say it failed
    DATA="{\"state\": \"failure\", \"context\": \"Deploy preview\", \"description\": \"Deployment failed\"}"
    curl -s -S -H "Content-Type: application/json" -H "Authorization: token $TOKEN" -d "$DATA" "$STATUSES_URL" >/dev/null
  fi
}

cd "$GITHUB_WORKSPACE" || exit 1
# Some websites are pulling into a website folder
if [ -d "website" ]; then
  cd website || exit 1
fi
setup_vars
setup_testing
build_site
result=$?
post_build_cleanup
if [ $result -ne 0 ]; then
  post_build_failed_preview
else
  post_build_deploy_preview
fi
exit $result
