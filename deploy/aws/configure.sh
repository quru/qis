#!/bin/bash

# Amazon EC2 software configuration, originally based on the Docker configuration,
# now invoked by the CloudFormation scripts

if [ $1 == "web-server" ] || [ $1 == "app-with-cache" ] || [ $1 == "full-server" ] || [ $1 == "database" ]; then
	
	# Configure Apache for the runtime environment
	HOSTNAME=$(hostname)
	#HOSTNAME=$(echo $(hostname) | awk -F '-' '{print $2 "." $3 "." $4 "." $5}') 
	HTTP_PROCESSES=2
	HTTP_THREADS=15
	HTTPS_PROCESSES=2
	HTTPS_THREADS=15
	PG_USER=qis
	PG_PASS=qispass
	PG_MAX_CONNECTIONS=100
	PG_SHARED_BUFFERS=400MB
	PG_EFFECTIVE_CACHE_SIZE=700MB
	
	APACHE_WORKERS_MAX=$(expr $HTTP_THREADS \* $HTTP_PROCESSES + $HTTPS_THREADS \* $HTTPS_PROCESSES \* 4)
	# This conf file might be Fedora specific
	
	APACHE_CONF_FILE=/etc/httpd/conf.modules.d/00-mpm.conf
	
	echo "ServerLimit $APACHE_WORKERS_MAX" >> $APACHE_CONF_FILE
	echo "MaxRequestWorkers $APACHE_WORKERS_MAX" >> $APACHE_CONF_FILE
	echo "MaxConnectionsPerChild 10000" >> $APACHE_CONF_FILE
	
	sed -i 's/.*ServerName.*/    ServerName '$HOSTNAME'/g' /etc/httpd/conf.d/qis.conf
	sed -i 's/.*WSGIDaemonProcess.*/    WSGIDaemonProcess qis user=qis group=apache processes='$HTTP_PROCESSES' threads='$HTTP_THREADS' python-path=\/opt\/qis\/src:\/opt\/qis\/lib\/python2.7\/site-packages:\/opt\/qis\/lib64\/python2.7\/site-packages/g' /etc/httpd/conf.d/qis.conf
	sed -i 's/.*ServerName.*/    ServerName '$HOSTNAME'/g' /etc/httpd/conf.d/qis-ssl.conf
	sed -i 's/.*WSGIDaemonProcess.*/    WSGIDaemonProcess qis-ssl user=qis group=apache processes='$HTTPS_PROCESSES' threads='$HTTPS_THREADS' python-path=\/opt\/qis\/src:\/opt\/qis\/lib\/python2.7\/site-packages:\/opt\/qis\/lib64\/python2.7\/site-packages/g' /etc/httpd/conf.d/qis-ssl.conf
		
	SETTINGS_FILE=/opt/qis/conf/local_settings.py
	SECRET_KEY=$(pwgen -s 32 1)
	let DB_POOL_SIZE=$HTTP_THREADS/2
	
	CACHE_PORT=11211
	DB_PORT=5432
	APACHE=0
	MEMCACHE=0
	POSTGRES=0
	LOAD_BALANCER=1
	DB_IP='127.0.0.1'
	CACHE_IP='127.0.0.1'	
	
	#Server is web only
	if [ $1 == "web-server" ]; then
		echo "Web only"
		#Checks that both arguments are valid ip addresses
		if [[ "$2" =~ ^([0-9]{1,3})[.]([0-9]{1,3})[.]([0-9]{1,3})[.]([0-9]{1,3})$ ]] && [[ "$3" =~ ^([0-9]{1,3})[.]([0-9]{1,3})[.]([0-9]{1,3})[.]([0-9]{1,3})$ ]]; then
			APACHE=1
			DB_IP=$2
			CACHE_IP=$3
		else
			echo "Error, Web-server needs ip of database and then cache"
		fi
	fi
	
	#Server is web and cache
	if [ $1 == "app-with-cache" ]; then
		echo "Web and cache"
		#Checks that the first argument is a valid ip address
		if [[ "$2" =~ ^([0-9]{1,3})[.]([0-9]{1,3})[.]([0-9]{1,3})[.]([0-9]{1,3})$ ]]; then
			APACHE=1
			MEMCACHE=1
			DB_IP=$2
		else
			echo "Error, app-with-cache server needs ip of database"
		fi
	fi
	
	#Server is web, cache and database
	if [ $1 == "full-server" ]; then
		echo "Web, cache and database"
		APACHE=1
		MEMCACHE=1
		POSTGRES=1
	fi
	#Server is database only
	if [ $1 == "database" ]; then
		echo "Database only"
		POSTGRES=1
	fi
	
	if [ $POSTGRES == 1 ] || [ $APACHE == 1 ]; then
		yum -y install nfs-utils nfs-utils-lib portmap
		sudo setsebool -P httpd_use_nfs on
		if ! [ $POSTGRES == 1 ] || ! [ $APACHE == 1 ]; then
			service rpcbind start
			service nfs start
		fi
	fi
	
	if [ $POSTGRES == 1 ]; then
		echo "Starting Postgres..."
		# Tune postgres.conf
		sudo -u postgres echo "max_connections = $PG_MAX_CONNECTIONS" >> /var/lib/pgsql/data/postgresql.conf
		sudo -u postgres echo "shared_buffers = $PG_SHARED_BUFFERS" >> /var/lib/pgsql/data/postgresql.conf
		sudo -u postgres echo "effective_cache_size = $PG_EFFECTIVE_CACHE_SIZE" >> /var/lib/pgsql/data/postgresql.conf
		sudo -u postgres echo "checkpoint_segments = 16" >> /var/lib/pgsql/data/postgresql.conf
		sudo -u postgres echo "checkpoint_completion_target = 0.9" >> /var/lib/pgsql/data/postgresql.conf
		sudo -u postgres echo "listen_addresses = '*'" >> /var/lib/pgsql/data/postgresql.conf
		sudo -u postgres echo "host    all    all    0.0.0.0/0    md5" >> /var/lib/pgsql/data/pg_hba.conf
		#THE_USER=${SUDO_USER:-${USERNAME:-unknown}}
		
		# Start Postgres in the background
		sudo -u postgres mkdir /var/lib/pgsql/data/pg_log && chmod 700 /var/lib/pgsql/data/pg_log
		
		sudo -u postgres /usr/bin/pg_ctl start -w -D /var/lib/pgsql/data -l /var/lib/pgsql/data/pg_log/qis_init.log -o '-i'

		# Create the QIS user and database
		sudo -u postgres psql -h localhost -U postgres -d postgres -c "CREATE ROLE $PG_USER WITH LOGIN PASSWORD '$PG_PASS'"
		sudo -u postgres createdb -h localhost -U postgres --owner $PG_USER qis-cache
		sudo -u postgres createdb -h localhost -U postgres --owner $PG_USER qis-mgmt
		# Stop background process, we now need to	 run it foreground
		### sudo -u postgres /usr/bin/pg_ctl stop -w -D /var/lib/pgsql/data
		### sudo -u postgres /usr/bin/postgres start -D /var/lib/pgsql/data
		
		#service postgresql start
	fi
	
	if [ $MEMCACHE == 1 ]; then
		echo "Starting Memcache..."
		service memcached start
	fi
	
	if [ $APACHE == 1 ]; then
		echo "Starting Apache..."
		service httpd start
	fi
	
	echo "" >> $SETTINGS_FILE
	echo "# Settings generated at $(date)" >> $SETTINGS_FILE
	echo "# Note 'cache' and 'db' servers are added to the hosts file by Docker" >> $SETTINGS_FILE
	echo "PUBLIC_HOST_NAME = \"$HOSTNAME\"" >> $SETTINGS_FILE
	echo "SECRET_KEY = \"$SECRET_KEY\"" >> $SETTINGS_FILE
	echo "MEMCACHED_SERVERS = [\"$CACHE_IP:$CACHE_PORT\"]" >> $SETTINGS_FILE
	echo "MGMT_DATABASE_CONNECTION = \"postgresql+psycopg2://$PG_USER:$PG_PASS@$DB_IP:$DB_PORT/qis-mgmt\"" >> $SETTINGS_FILE
	echo "MGMT_DATABASE_POOL_SIZE = $DB_POOL_SIZE" >> $SETTINGS_FILE
	echo "CACHE_DATABASE_CONNECTION = \"postgresql+psycopg2://$PG_USER:$PG_PASS@$DB_IP:$DB_PORT/qis-cache\"" >> $SETTINGS_FILE
	echo "CACHE_DATABASE_POOL_SIZE = $DB_POOL_SIZE" >> $SETTINGS_FILE

	if [ $LOAD_BALANCER == 1 ]; then
		echo "PROXY_SERVERS = 1" >> $SETTINGS_FILE
	fi
	
else
	echo "First parameter needs to be type of server"
fi
