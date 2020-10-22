#!/bin/bash
STATUSES_URL=$(jq -r ".pull_request.statuses_url" $GITHUB_EVENT_PATH)
DATA="{\"state\": \"pending\", \"target_url\": \"\", \"context\": \"Deploy preview\", \"description\": \"Waiting for site to build\"}"
curl -s -S -H "Content-Type: application/json" -H "Authorization: token $TOKEN" -d "$DATA" "$STATUSES_URL" >/dev/null
