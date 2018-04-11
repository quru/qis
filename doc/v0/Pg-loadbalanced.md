# The use of multiple Postgres databases with QIS on RHEL/CentOS 6

Current status: unmaintained since 2013

## Introduction

This document assumes that you have SSH'd onto two (or more) previous hardened and up to date Red Hat 6 / Centos 6 or similar server and have successfully installed and run QIS from each.

This document describes how to use PG_POOL to share the same databases across all instances so that the user permissions and cache become highly available without the requirement for a dedicated PostgreSQL cluster.

## Conventions
Any code that you are required to enter on your QIS host is shown

    As a code block

If you are required to enter a command into a terminal then it will have a prompt shown

    $ like this


# Install PGPOOL

## Basic install

PG_POOL can only be installed through the correct repo. This means adding "pgdg-redhat-8.4-3" to the /etc/yum.repos.d configuration. Fortunately there is an RPM file to do this for you.

    $ sudo rpm -Uvh http://yum.pgrpms.org/8.4/redhat/rhel-6-x86_64/pgdg-redhat-8.4-3.noarch.rpm
    
With this, it should now be possible to find pg_pool via a Yum search and to install it

    $ sudo yum install pgpool-II-84
    

## Configure the pgpool settings

There are some sample configs in /etc/pgpool-II-84. We will start from the pgpool.conf.sample document

    $ sudo cp /etc/pgpool-II-84/pgpool.conf.sample /etc/pgpool-II-84/pgpool.conf
    
Then, using your preferred editor change:

* listen_addresses = 'localhost' to listen_addresses = '*'
* replication_mode = false to replication_mode = true
* load_balance_mode = false to load_balance_mode = true

Then change the backend_hostname, backend_port and backend_weight to the following:

    # backend_hostname, backend_port, backend_weight
    # here are examples
    backend_hostname0 = '119.27.36.93'
    backend_port0 = 5432
    backend_weight0 = 1
    backend_data_directory0 = '/var/lib/pgsql/8.4/data'
    backend_hostname1 = '119.27.36.94'
    backend_port1 = 5432
    backend_weight1 = 1
    backend_data_directory1 = '/var/lib/pgsql/8.4/data'

and save the file.

## Configure the pcp settings

There should also be a pcp.conf.sample in the same directory. This is needed for the pgpool admin. Copy this file:

    $ sudo cp /etc/pgpool-II-84/pcp.conf.sample /etc/pgpool-II-84/pcp.conf

and then edit it, changing the last line to include a valid userid and md5 password such as

    qispool:eb2d69e888b1a502c0600eb29018b034
    
and save the file.

## Edit pg_hba.conf

pg_hba.conf controls the access to the PostgreSQL database at a host level. By default it is set to allow only localhost access. We need to allow pgpool on all the nodes to be able to access it.

Edit the file at at the bottom add something like:

    host    all         all         <ip_of_node_1>/32       trust
    host    all         all         <ip_of_node_2>/32       trust

putting the correct IP addresses in place in the 4th column. Add a row for each node. Alternatively you can open up the connection to the subnet or any other valid IP range.

## Edit the postgresql.conf
By default, postgresql.conf only allows postgres to listen on the localhost. Therefore, in /var/lib/pgsql/data/postgresql.conf change 

    listen_addresses = 'localhost'

to

    listen_addresses = '*'
    

# Check the firewall

If you are running IPTables on either of your hosts, you will have to open it up to port 9999 (assuming that this is still the pgpool port) and the default 5432 to allow other notes to connect to the local PostgreSQL server. If you are using IPtables add something like:

    -A INPUT -p tcp -s <your ip subnet> --dport 5432 -j ACCEPT
    -A INPUT -p tcp -s <your ip subnet> --dport 9999 -j ACCEPT
    -A INPUT -p tcp -s <your ip subnet> --dport 9898 -j ACCEPT

to your /etc/sysconfig/iptables document at an appropriate place. Note that port 9898 is used for the pgpool admin.
    
# Copy the database to all the database nodes

You need to make sure that all of the databases have the same data. On the one that you have identified as the source run

    $ sudo su --command="pg_dump -c qis-mgmt -f /path/to/backup/qis-mgmt.sql" postgres
    $ sudo su --command="pg_dump -c qis-cache -f /path/to/backup/qis-cache.sql" postgres
    
and on the targets (having copied the back-ups across) run

    $ sudo su --command="psql -U postgres -f /path/to/backup/qis-mgmt.sql" postgres
    $ sudo su --command="psql -U postgres -f /path/to/backup/qis-cache.sql" postgres

# Starting pgpool

To start pgpool, you will need to restart the PostgreSQL service

    $ sudo service postgresql restart
    
Then you will need to start up pgpool. However, it is likely that the service script will have an error in it, looking for /etc/pgpool-II rather than /etc/pgpool-II-84 so create an alias to correct it and then start the service:
    
    $ sudo ln -s /etc/pgpool-II-84/ /etc/pgpool-II
    $ sudo service pgpool-II-84 start
