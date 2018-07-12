#!/bin/bash

# Runs a simple check to test that the QIS service is running

curl -A "curl/docker healthcheck" -s "http://localhost/api/v1/list/?path=/&limit=1" | grep -e '"status":[\s]*200' || exit 1
