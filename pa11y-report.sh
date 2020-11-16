#!/bin/bash

function docker_pa11y() {
    docker run --rm \
      -t \
      -v /etc/passwd:/etc/passwd:ro \
      -v /etc/group:/etc/group:ro \
      -u "$(id -u)":"$(id -g)" \
      -v "$GITHUB_WORKSPACE":/home/tmp \
      linaroits/pa11y-ci "$@"
}

echo "Producing HTML report for $1"
docker_pa11y pa11y-ci-reporter-html -s "/home/tmp/$1.json" -d "/home/tmp/$1"
