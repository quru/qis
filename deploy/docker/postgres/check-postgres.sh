#!/bin/bash

# Runs a simple check to test that the Postgres database is accepting connections.

psql -h localhost -U qis -d qis-mgmt -c "select 'alive';" || exit 1
