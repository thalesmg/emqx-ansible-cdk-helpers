#!/usr/bin/env bash

set -xuo pipefail

pgrep -a beam.smp | grep '/root/emqtt-bench/emqtt_bench' | grep -v remsh | awk '{ print $1; }' | xargs kill -9 || true;
pkill -f -9 run-tests.py || true
