#!/bin/bash
# shellcheck disable=SC2154
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
if [ -n "$1" ]; then
    if [ ! -d "$1" ]; then
        echo "$1 is not a directory"
        exit 1
    fi
    if [ -d "$1/_data" ] && [ -f "$1/_data/routingrules.json" ]; then
        cd $DIR
        echo "Processing $1/_data/routingrules.json"
        pipenv run python lambda-redirect.py -r "$1/_data/routingrules.json"
    else
        echo "No routing rules - skipping"
    fi
else
    echo "No parameters provided - skipping"
fi
