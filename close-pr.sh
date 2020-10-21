#!/bin/bash
PR_NUMBER=$(jq -r ".pull_request.number" $GITHUB_EVENT_PATH)
echo "Cleaning up after $PR_NUMBER has closed"
BUILDDIR="$AWS_STATIC_SITE_URL-$PR_NUMBER"
if [ -d "$BUILDDIR" ]; then
    echo "Removing website review directory"
    rm -rf "$BUILDDIR"
else
    echo "No website review directory ($BUILDDIR) to remove"
fi
A11YDIR="/srv/a11y.linaro.org/$AWS_STATIC_SITE_URL-$PR_NUMBER.websitepreview.linaro.org"
if [ -d "$A11YDIR" ]; then
    echo "Removing $A11YDIR"
    rm -rf "$A11YDIR"
else
    echo "No a11y test ($A11YDIR) to remove"
fi
