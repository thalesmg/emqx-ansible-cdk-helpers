#!/bin/bash

set -xu

sudo systemctl stop emqx
sudo emqx stop
sudo rm -rf /var/lib/emqx/mnesia/*
sudo emqx start
