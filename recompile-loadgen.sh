#!/usr/bin/env bash

set -xeu

cd /root/emqtt-bench

BENCH_BRANCH=${1:-tmg-test2}

git fetch -a
git checkout "${BENCH_BRANCH}"
git pull -r
# rm -rf _build/ || true

make
