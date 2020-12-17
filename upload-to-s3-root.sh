#!/bin/bash
# shellcheck disable=SC2154
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "/srv/s3-staging/$SITE_URL" || exit 1
# Sync HTML files with different cache settings. Using "no-cache" does *NOT* mean that the file is not
# cached - it just forces the browser to do a quick check upstream to make sure that the page is valid.
aws --profile "$AWS_STATIC_SITE_PROFILE" s3 sync --exclude "*" --include "*.html" --cache-control "no-cache, max-age=86400" ./ "s3://$AWS_STATIC_SITE_URL" --delete
# Sync non-HTML files with "normal" cache settings.
aws --profile "$AWS_STATIC_SITE_PROFILE" s3 sync --include "*" --exclude "*.html" --cache-control "public, max-age=86400" ./ "s3://$AWS_STATIC_SITE_URL" --delete
cd $DIR
pipenv run python set_last_modified_meta.py
