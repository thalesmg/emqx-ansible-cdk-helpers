#!/bin/bash

set -eu

LG_NUM=$1
OUTPUT_RECORDING=$2

{% if (groups['replicants'] | default([])) %}
# Note: targeting only replicants when they exist
TARGET="emqx-$(( {{ emqx_num_cores }} + $LG_NUM % {{ (groups['replicants'] | default([])) | length }} )).int.{{ emqx_cluster_name }}"
{% else %}
TARGET="emqx-$(( $LG_NUM % {{ groups['emqx'] | length }} )).int.{{ emqx_cluster_name }}"
{% endif %}

START_NUM=$(( $LG_NUM * {{ emqtt_bench_number_of_connections }} ))

cd /root/emqtt-bench/

{
  env TZ={{ script_timezone }} date
  time ./with-ipaddrs.sh ./emqtt_bench sub \
       -c {{ emqtt_bench_number_of_connections }} \
       -i {{ emqtt_bench_interval }} \
       -x {{ emqtt_bench_session_expiry_interval }} \
       -t 'bench/%i/#' \
       {{ "--lowmem" if (emqtt_bench_lowmem_mode | default(False) | bool) else "" }} \
       -n "$START_NUM" \
       {{ "--prefix \"" + emqtt_bench_prefix + "\"" if emqtt_bench_prefix is defined else "" }} \
       {{ "--shortids" if (emqtt_bench_shortids | default(False) | bool) else "" }} \
       -h $TARGET 2>&1
} > "/tmp/$OUTPUT_RECORDING.$LG_NUM.sub"
