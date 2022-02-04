#!/bin/bash
# shellcheck disable=SC2154
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
if [ -n "$1" ]; then
    PARM1="$1"
    # Some push workflows don't provide the / at the end so check and
    # add if missing.
    LAST="${$PARM1: -1}"
    if [ "$LAST" != "/" ]; then
        PARM1="$PARM1/"
    fi
    if [ ! -d "$PARM1" ]; then
        echo "$PARM1 is not a directory"
        exit 1
    fi
    if [ -d "$PARM1_data" ] && [ -f "$PARM1_data/routingrules.json" ]; then
        cd $DIR
        echo "Processing $PARM1_data/routingrules.json"
        pipenv run python lambda_redirect.py -r "$PARM1_data/routingrules.json"
    else
        echo "No routing rules - skipping"
    fi
else
    echo "No parameters provided - skipping"
fi
