#!/usr/bin/env bash

set -xeu

RATE=$1

PUBNODE=$(epmd -names | awk '/name/{print $2}' | grep pub || true)

if [ -n "$PUBNODE" ]; then
  sudo erl -sname $RANDOM -noinput -eval "
      {ok, Host} = inet:gethostname(),
      Node = list_to_atom(\"$PUBNODE@\" ++ Host),
      true = net_kernel:hidden_connect_node(Node),
      X = erpc:call(Node, fun() ->
        application:set_env(emqtt_bench, pub_interval, $RATE),
        application:get_env(emqtt_bench, pub_interval)
      end),
      init:stop().
      " 2>&1
  echo done
else
  echo "node not running!"
fi
