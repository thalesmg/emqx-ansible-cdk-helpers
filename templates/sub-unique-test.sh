#!/bin/bash

set -eu

LG_NUM=$1
OUTPUT_RECORDING=$2

{% if groups['replicants'] %}
# Note: targeting only replicants when they exist
TARGET="emqx-$(( {{ emqx_num_cores }} + $LG_NUM % {{ groups['replicants'] | length }} )).int.{{ emqx_cluster_name }}"
{% else %}
TARGET="emqx-$(( $LG_NUM % {{ groups['emqx'] | length }} )).int.{{ emqx_cluster_name }}"
{% endif %}

cd /root/emqtt-bench/

{
  env TZ={{ script_timezone }} date
  time ./with-ipaddrs.sh ./emqtt_bench sub \
       -c {{ emqtt_bench_number_of_connections }} \
       -i {{ emqtt_bench_interval }} \
       -x {{ emqtt_bench_session_expiry_interval }} \
       -t 'bench/%c/#' \
       {{ "--lowmem" if (emqtt_bench_lowmem_mode | default(False) | bool) else "" }} \
       {{ "--prefix " + emqtt_bench_prefix if emqtt_bench_prefix is defined else "" }} \
       -h $TARGET 2>&1
} > "/tmp/$OUTPUT_RECORDING"
