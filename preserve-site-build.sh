#!/bin/bash
cd "$GITHUB_WORKSPACE" || exit 1
# We should have a directory already built now ...
if [ -d "$SITE_URL" ]; then
    echo "Preserving $SITE_URL"
    mv "$SITE_URL" /srv/site-builds/
else
    echo "No built site ($SITE_URL) found!"
fi
