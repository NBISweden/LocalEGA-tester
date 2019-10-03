#!/bin/bash

if [ "${TRAVIS_TAG}" ]; then
    docker push "${DOCKER_REPO}:${TRAVIS_TAG}"
fi
docker push "${DOCKER_REPO}:${TRAVIS_COMMIT::6}"