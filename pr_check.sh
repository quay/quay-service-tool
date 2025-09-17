#!/bin/bash
set -exv

IMAGE="quay.io/app-sre/quay-service-tool"
TAG_PR_CHECK="pr-check"

docker build -t "${IMAGE}:${TAG_PR_CHECK}" -f Dockerfile .
