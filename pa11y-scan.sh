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

cd "$GITHUB_WORKSPACE"
echo "Checking web site $1"
docker_pa11y pa11y-ci --sitemap "https://$1/sitemap.xml" --sitemap-exclude ".+\.pdf" -j > "$1.json"
# pa11y returns 2 if the site has errors so we need to return a zero error back to Bamboo
exit 0
