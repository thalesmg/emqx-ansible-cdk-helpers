#!/bin/bash

set -eu

{
  # NB: Those are present in `os_common.sh` in CDK with higher
  # numbers...
  # # 2 millions system-wide
  # sysctl -w fs.file-max=2097152
  # sysctl -w fs.nr_open=2097152
  # echo 2097152 > /proc/sys/fs/nr_open
  # # for the current session
  # ulimit -n 2097152

  # Increase number of incoming connections backlog:
  sysctl -w net.core.somaxconn=32768
  sysctl -w net.ipv4.tcp_max_syn_backlog=16384
  sysctl -w net.core.netdev_max_backlog=16384

  # local port range
  # sysctl -w net.ipv4.ip_local_port_range='1000 65535'
  # TMG FIXME: had to use this:
  # Already present in `os_common.sh`...
  # sysctl -w net.ipv4.ip_local_port_range='1025 65535'

  # TCP Socket read/write buffer:
  # sysctl -w net.core.rmem_default=262144
  # sysctl -w net.core.wmem_default=262144
  # sysctl -w net.core.rmem_max=16777216
  # sysctl -w net.core.wmem_max=16777216
  sysctl -w net.core.optmem_max=16777216

  # sysctl -w net.ipv4.tcp_mem='16777216 16777216 16777216'
  sysctl -w net.ipv4.tcp_rmem='1024 4096 16777216'
  sysctl -w net.ipv4.tcp_wmem='1024 4096 16777216'

  # TMG FIXME: Outdated or module not loaded; ignore
  # TCP connection tracking:
  # sysctl -w net.nf_conntrack_max=1000000
  # sysctl -w net.netfilter.nf_conntrack_max=1000000
  # sysctl -w net.netfilter.nf_conntrack_tcp_timeout_time_wait=30

  # TIME-WAIT Bucket Pool, Recycling and Reuse:
  sysctl -w net.ipv4.tcp_max_tw_buckets=1048576

  # Enabling following option is not recommended. It could cause connection reset under NAT
  # sysctl -w net.ipv4.tcp_tw_recycle=1
  # sysctl -w net.ipv4.tcp_tw_reuse=1

  # Timeout for FIN-WAIT-2 Sockets:
  sysctl -w net.ipv4.tcp_fin_timeout=15

  # William's config
  sysctl -w net.core.rmem_default=262144000
  sysctl -w net.core.wmem_default=262144000
  sysctl -w net.core.rmem_max=262144000
  sysctl -w net.core.wmem_max=262144000
  sysctl -w net.ipv4.tcp_mem="378150000  504200000  756300000"
}
