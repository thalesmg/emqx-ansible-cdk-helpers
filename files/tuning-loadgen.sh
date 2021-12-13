#!/bin/bash

set -eu

{
  # already set in `os_common.sh`
  # sysctl -w net.ipv4.ip_local_port_range="1025 65535"
  # echo 1000000000 > /proc/sys/fs/nr_open
  # ulimit -n 1000000000

  # William's config
  sysctl -w net.core.rmem_default=262144000
  sysctl -w net.core.wmem_default=262144000
  sysctl -w net.core.rmem_max=262144000
  sysctl -w net.core.wmem_max=262144000
  sysctl -w net.ipv4.tcp_mem="378150000  504200000  756300000"
}
