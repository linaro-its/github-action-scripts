#!/bin/bash
cd "$GITHUB_WORKSPACE" || exit 1
# If there is a previously built site, move it
# into the workspace (after the repo has been
# fetched) so that the build process doesn't take
# too long (e.g. images).
if [ -d "/srv/site-builds/$SITE_URL" ]; then
    echo "Restoring last site build for $SITE_URL"
    mv "/srv/site-builds/$SITE_URL" .
else
    echo "No previous site build for $SITE_URL"
fi
