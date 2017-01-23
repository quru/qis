#!/bin/bash

# Runs a single instance of memcached.
# This script expects to be run as the root user.

exec /usr/bin/memcached -u memcache -m $MEMCACHED_SIZE
