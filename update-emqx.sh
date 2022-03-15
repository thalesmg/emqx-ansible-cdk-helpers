#!/bin/bash

set -exu

cd /root/emqx

rm mix.lock rebar.lock || true

EMQX_BUILDER_IMAGE="ghcr.io/emqx/emqx-builder/5.0-8:1.13.3-24.2.1-1-ubuntu20.04"
EMQX_BRANCH="perf-test-mnesia-post-commit-hook-patches1"
# EMQX_BRANCH="perf-test-master"

git checkout "${EMQX_BRANCH}"
git pull -r

rm -rf ./_packages || true

make clean-all

docker run --rm -i \
           -v "$PWD":/emqx \
           -w /emqx \
           -e EMQX_NAME="emqx" \
           -e HOME="/root" \
           "$EMQX_BUILDER_IMAGE" \
           bash -c "make emqx-elixir-pkg"

yes N | dpkg -i ./_packages/emqx/*.deb
