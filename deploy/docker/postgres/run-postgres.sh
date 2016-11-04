#!/bin/bash

# Runs the Postgres service with settings from the Docker image and run command.
# On first run, creates the QIS database role and a new empty database.
# This script expects to be run as the postgres user.

PG_BIN_DIR=/usr/lib/postgresql/9.5/bin
PG_CONF_FILE=$PGDATA/postgresql.conf
FIRST_RUN_LOG_FILE=$PGDATA/pg_log/first_run.log

if [ ! -f "$FIRST_RUN_LOG_FILE" ]; then

	# Tune postgres.conf
	echo "max_connections = $PG_MAX_CONNECTIONS" >> $PG_CONF_FILE
	echo "shared_buffers = $PG_SHARED_BUFFERS" >> $PG_CONF_FILE
	echo "effective_cache_size = $PG_EFFECTIVE_CACHE_SIZE" >> $PG_CONF_FILE

	# Optional - save daily logs (max 7) to the data volume
	#echo "logging_collector = on" >> $PG_CONF_FILE
	#echo "log_filename = 'postgresql-%a.log'" >> $PG_CONF_FILE
	#echo "log_truncate_on_rotation = on" >> $PG_CONF_FILE
	#echo "log_rotation_age = 1d" >> $PG_CONF_FILE

	# Start Postgres in the background
	mkdir $PGDATA/pg_log && chmod 700 $PGDATA/pg_log
	$PG_BIN_DIR/pg_ctl start -w -l $FIRST_RUN_LOG_FILE

	# Create the QIS user and database
	psql -h localhost -U postgres -d postgres -c "CREATE ROLE \"$PG_USER\" WITH LOGIN PASSWORD '$PG_PASSWORD'"
	createdb -h localhost -U postgres --owner $PG_USER qis-cache
	createdb -h localhost -U postgres --owner $PG_USER qis-mgmt

	# Stop background process, we now need to run it foreground
	$PG_BIN_DIR/pg_ctl stop -w
fi

# Run the main Docker process (the container exits when this returns)
exec $PG_BIN_DIR/postgres
