#!/usr/bin/env bash

set -xeu

cd /root/emqttb

BENCH_BRANCH=${1:-master}

git fetch -a
git checkout "${BENCH_BRANCH}"
git pull -r
# rm -rf _build/ || true

env BUILD_WITHOUT_QUIC=1 ./rebar3 compile
