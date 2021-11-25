#!/bin/bash
# shellcheck disable=SC2154
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
if [ -n "$1" ]; then
    if [ ! -d "$1" ]; then
        echo "$1 is not a directory"
        exit 1
    fi
    if [ -d "$1_data" ] && [ -f "$1_data/routingrules.json" ]; then
        cd $DIR
        echo "Processing $1_data/routingrules.json"
        pipenv run python lambda_redirect.py -r "$1_data/routingrules.json"
    else
        echo "No routing rules - skipping"
    fi
else
    echo "No parameters provided - skipping"
fi
