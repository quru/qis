#!/bin/bash

# Configure and run a QIS database server (PostgreSQL instance) based
# on the environment variables from the Docker image and run command.
# This script expects to be run as the postgres user.

if [ ! -f "/var/lib/pgsql/data/pg_log/qis_init.log" ]; then
	# Tune postgres.conf
	echo "max_connections = $PG_MAX_CONNECTIONS" >> /var/lib/pgsql/data/postgresql.conf
	echo "shared_buffers = $PG_SHARED_BUFFERS" >> /var/lib/pgsql/data/postgresql.conf
	echo "effective_cache_size = $PG_EFFECTIVE_CACHE_SIZE" >> /var/lib/pgsql/data/postgresql.conf

	# Start Postgres in the background
	mkdir /var/lib/pgsql/data/pg_log && chmod 700 /var/lib/pgsql/data/pg_log
	/usr/bin/pg_ctl start -w -D /var/lib/pgsql/data -l /var/lib/pgsql/data/pg_log/qis_init.log

	# Create the QIS user and database
	psql -h localhost -U postgres -d postgres -c "CREATE ROLE $PG_USER WITH LOGIN PASSWORD '$PG_PASS'"
	createdb -h localhost -U postgres --owner $PG_USER qis-cache
	createdb -h localhost -U postgres --owner $PG_USER qis-mgmt

	# Stop background process, we now need to run it foreground
	/usr/bin/pg_ctl stop -w -D /var/lib/pgsql/data
fi

# Run the main Docker process (the container exits when this returns)
/usr/bin/postgres -D /var/lib/pgsql/data
