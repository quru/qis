#!/bin/bash

# Runs the Postgres service with settings from the Docker image and run command.
# On first run, creates the QIS database role and a new empty database.
# This script expects to be run as the postgres user.

PG_BIN_DIR=/usr/lib/postgresql/9.5/bin
PG_CONF_FILE=$PGDATA/postgresql.conf
FIRST_RUN_FILE=$PGDATA/first_run.log

# Check that the PGDATA directory is accessible from the container
if [ ! -w $PGDATA ]; then
  echo "The PGDATA directory is not writable for the container user $USER."
  echo "Ensure that the path exists as a volume or host-mounted directory"
  echo "and has write permissions for the container user."
  echo $PGDATA
  exit 1
fi

# On first run, create the Postgres "cluster"
if [ ! -f $PG_CONF_FILE ]; then

	echo "Initialising new data directory at $PGDATA"
	$PG_BIN_DIR/initdb --locale=en_GB.UTF-8

	# Require passwords for external connections
	echo "host    all             all             0.0.0.0/0               md5" >> $PGDATA/pg_hba.conf

	# Enable external TCP connections, set logging to stderr for Docker to pick up
	echo "listen_addresses = '*'" >> $PG_CONF_FILE && \
	echo "log_destination = 'stderr'" >> $PG_CONF_FILE

	# Tune postgres.conf
	echo "max_connections = $PG_MAX_CONNECTIONS" >> $PG_CONF_FILE
	echo "shared_buffers = $PG_SHARED_BUFFERS" >> $PG_CONF_FILE
	echo "effective_cache_size = $PG_EFFECTIVE_CACHE_SIZE" >> $PG_CONF_FILE

	# Optional - save daily logs (max 7) to the data volume
	#echo "logging_collector = on" >> $PG_CONF_FILE
	#echo "log_filename = 'postgresql-%a.log'" >> $PG_CONF_FILE
	#echo "log_truncate_on_rotation = on" >> $PG_CONF_FILE
	#echo "log_rotation_age = 1d" >> $PG_CONF_FILE
fi

# On first run, create the database
if [ ! -f "$FIRST_RUN_FILE" ]; then

	echo "Starting background Postgres to create the database"
	$PG_BIN_DIR/pg_ctl start -w -l $FIRST_RUN_FILE

	echo "Creating the QIS database role and new empty database"
	psql -h localhost -U postgres -d postgres -c "CREATE ROLE \"$PG_USER\" WITH LOGIN PASSWORD '$PG_PASSWORD'"
	createdb -h localhost -U postgres --owner $PG_USER qis-cache
	createdb -h localhost -U postgres --owner $PG_USER qis-mgmt

	echo "Stopping background Postgres, about to start normally"
	$PG_BIN_DIR/pg_ctl stop -w
fi

# Run the main Docker process (the container exits when this returns)
exec $PG_BIN_DIR/postgres
