#!/bin/bash
if [ ! -d "$1" ]; then
    echo "No output from pa11y-ci-reporter-html"
    exit 1
fi

if [ -d "/srv/a11y.linaro.org/$1" ]; then
    echo "Removing previous report directory for $1"
    rm -rf "/srv/a11y.linaro.org/$1"
fi
mv "$1" /srv/a11y.linaro.org/
