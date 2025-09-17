#!/bin/bash

# AppSRE team CD

set -exv

CURRENT_DIR=$(dirname $0)

IMAGE="quay.io/app-sre/quay-service-tool"
TAG_GIT_HASH=`git rev-parse --short=7 HEAD`
TAG_LATEST="latest"

# build the image
docker build -t "${IMAGE}:${TAG_LATEST}" -f Dockerfile .

# push the image to quay (Latest)
skopeo copy --dest-creds "${QUAY_USER}:${QUAY_TOKEN}" \
    "containers-storage:${IMAGE}:${TAG_LATEST}" \
    "docker://${IMAGE}:${TAG_LATEST}"

# push the image to quey (Git Hash)
skopeo copy --dest-creds "${QUAY_USER}:${QUAY_TOKEN}" \
    "containers-storage:${IMAGE}:${TAG_LATEST}" \
    "docker://${IMAGE}:${TAG_GIT_HASH}"
