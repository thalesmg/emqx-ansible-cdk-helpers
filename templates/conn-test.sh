#!/bin/bash

set -eu

LG_NUM=$1
OUTPUT_RECORDING=$2

TARGET="emqx-$(( $LG_NUM % {{ groups['emqx'] | length }} )).int.{{ emqx_cluster_name }}"

cd /root/emqtt-bench/

{
  env TZ={{ script_timezone }} date
  time ./with-ipaddrs.sh ./emqtt_bench conn \
       -c {{ emqtt_bench_number_of_connections }} \
       -i {{ emqtt_bench_interval }} \
       {{ "--lowmem" if (emqtt_bench_lowmem_mode | default(False) | bool) else "" }} \
       -h $TARGET  2>&1
} > "/tmp/$OUTPUT_RECORDING"
