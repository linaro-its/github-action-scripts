#!/bin/bash
# shellcheck disable=SC2154
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "/srv/s3-staging/$SITE_URL" || exit 1
aws --profile "$AWS_STATIC_SITE_PROFILE" s3 sync --cache-control "public, max-age=86400" ./ "s3://$BAMBOO_AWS_STATIC_SITE_URL" --delete
$DIR/set_last_modified_meta.py
