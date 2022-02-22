#!/bin/bash
# shellcheck disable=SC2154
set -e
# NEW_CHANGES=""
# # See if we've got any output from the S3 upload script
# if [ -f "/tmp/$GITHUB_SHA.tmp" ]; then
#     cat "/tmp/$GITHUB_SHA.tmp"
#     CHANGES=$(grep upload /tmp/$GITHUB_SHA.tmp | awk '{print $2}')
#     # Need to ensure that each change starts with "/" either by removing
#     # a leading full-stop or by adding a missing "/"
#     for change in $CHANGES
#     do
#         if [[ ${change::1} == "." ]]; then
#             new_change=${change:1}
#         elif [[ ${change::1} == "/" ]]; then
#             new_change=change
#         else
#             new_change="/${change}"
#         fi
#         NEW_CHANGES="$NEW_CHANGES $new_change"
#     done
#     # Clean up ...
#     rm "/tmp/$GITHUB_SHA.tmp"
# fi

# if [ "$NEW_CHANGES" == "" ]; then
#     NEW_CHANGES="/*"
# fi

# Intelligent cache invalidation seems to cause problems when error responses are cached
# since the intelligent invalidation doesn't always touch those paths. For now, revert to
# invalidating the entire site.
NEW_CHANGES="/*"

echo "======== CREATING INVALIDATION ========"
echo "--distribution-id \"$CF_DIST_ID_STATIC_LO\" --paths $NEW_CHANGES"
invID=$(aws --profile "$AWS_STATIC_SITE_PROFILE" cloudfront create-invalidation \
--distribution-id "$CF_DIST_ID_STATIC_LO" --paths "$NEW_CHANGES" --query Invalidation.Id --output text)
export invID

echo "======== INVALIDATION ID ========"
echo "${invID}"

echo "======== POLLING COMPLETED INVALIDATION ========"
# Increasingly, a single call to cloudfront wait invalidation-completed has been erroring
# out with "max attempts exceeded". We now run this in a do loop to ensure that we repeat
# the call until it is all finished.
until aws --profile "$AWS_STATIC_SITE_PROFILE" cloudfront wait invalidation-completed \
            --distribution-id "$CF_DIST_ID_STATIC_LO" --id "${invID}" 2>/dev/null
do
    # Still waiting - output some progress
    echo "Still waiting ..."
    aws --profile "$AWS_STATIC_SITE_PROFILE" cloudfront get-invalidation \
    --distribution-id "$CF_DIST_ID_STATIC_LO" --id "${invID}"
    sleep 10
done

# and final confirmation
aws --profile "$AWS_STATIC_SITE_PROFILE" cloudfront get-invalidation \
--distribution-id "$CF_DIST_ID_STATIC_LO" --id "${invID}"

echo "======== INVALIDATION COMPLETED ========"
