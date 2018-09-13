# Upgrading Postgres

The basic Postgres upgrade procedure is [documented here](https://www.postgresql.org/docs/10/static/upgrading.html)
on the Postgres web site. This document adds to that a few QIS-specific steps to
make the process _easier_ to follow, though it is still not actually easy.

Postgres ships with a `pg_upgrade` command, but this does not appear to be any
simpler to use than the traditional "dump and reload" method, so the latter is
what is documented here.

The database must be shut down when performing an upgrade. During this time QIS
will continue to serve cached images, but will return errors for images that need
to be generated.

These steps document the changes required to migrate a QIS database from the stock
Postgres 8.4 package to Postgres v9.6 on a Red Hat Enterprise Linux 6 system.

## Upgrade procedure

### Know the file locations

On RHEL 6, the stock Postgres package installs files at:

* `/usr/lib64/pgsql/` - client libraries
* `/usr/share/pgsql/` - support and sample files
* `/var/lib/pgsql/` - default PGDATA location (server data and configuration files)

The newer version installs to different directories, so it is safe to install the
new version alongside the old. This makes upgrading easier and rolling back to the
old version possible. The new version equivalent locations are:

* `/usr/pgsql-9.6/lib/`
* `/usr/pgsql-9.6/share/`
* `/var/lib/pgsql/9.6/`

Additionally, the old service name is `postgresql` while the new one is
`postgresql-9.6`.

### Install the new version

Install the operating system specific Postgres [package repository](https://www.postgresql.org/download/)
and then install the new packages:

    $ sudo yum install https://download.postgresql.org/pub/repos/yum/9.6/redhat/rhel-6-x86_64/pgdg-redhat96-9.6-3.noarch.rpm
    $ sudo yum install postgresql96 postgresql96-server

### Back-up the old configuration files

    $ mkdir ~/pgbackup
    $ sudo cp /var/lib/pgsql/data/pg_hba.conf ~/pgbackup/
    $ sudo cp /var/lib/pgsql/data/postgresql.conf ~/pgbackup/

### Disable QIS's database access

Any changes made while the database is being exported will not be present after
the upgrade has completed, so it is better to stop QIS from accessing the database
at all. Also to make the data migration easier, we will allow other local users
to have `trust` access to the old database.

Edit `/var/lib/pgsql/data/pg_hba.conf`, comment out the old authentication rules
and add:

    # Temporary authentication for Postgres migration
    local  all  qis                reject
    host   all  qis  127.0.0.1/32  reject
    host   all  qis  ::1/128       reject
    local  all  all                trust
    host   all  all  127.0.0.1/32  trust
    host   all  all  ::1/128       trust

Then restart the service for these changes to take effect:

    $ sudo service postgresql restart

### Export the old database

Optionally delete the QIS image statistics, data which often makes up the vast
majority of the database size:

    $ psql -h localhost -U postgres -c "DELETE FROM systemstats" qis-mgmt
    $ psql -h localhost -U postgres -c "DELETE FROM imagestats" qis-mgmt

Optionally delete the QIS cache data, which also does not have to be migrated:

    $ psql -h localhost -U postgres -c "DELETE FROM cachectl" qis-cache

Then, using the newer Postgres version, export all the old databases, objects and
roles:

    $ export PATH=/usr/pgsql-9.6/bin:$PATH
    $ pg_dumpall -h localhost -U postgres -f ~/pgbackup/pg-databases.dump

### Switch the active Postgres service over to the new version

    $ sudo service postgresql stop
    $ sudo chkconfig postgresql off

    $ sudo service postgresql-9.6 initdb
    $ sudo chkconfig postgresql-9.6 on
    $ sudo service postgresql-9.6 start

### Re-apply the configuration

Apply any customised `pg_hba.conf` authentication rules from the old database cluster
to the new one at `/var/lib/pgsql/9.6/data/pg_hba.conf`. But keep these commented
out for now and add the temporary rule for `local  all  all    trust` so that
local users still have `trust` access.

Apply the customised `postgresql.conf` settings from the old database cluster to
the new one at `/var/lib/pgsql/9.6/data/postgresql.conf`. Move all the overridden
settings to the end of the new file so that they are easily identified in future.
See the QIS [installation guide](install.md) for a list of Postgres settings that
are likely to have been modified, but at the time of writing this incudes:

* `listen_addresses`, `port`, `max_connections`, `shared_buffers`, `wal_buffers`,
  `checkpoint_segments`, `checkpoint_completion_target`, `effective_cache_size`,
  `log_*`

In Postgres 9.6+, `checkpoint_segments` has been removed and `wal_buffers` is now
automatic, so do not re-apply these.

Once the configuration has been migrated, restart Postgres:

    $ sudo service postgresql-9.6 restart

On failure to start, check the new log file in `/var/lib/pgsql/9.6/data/pg_log/`,
or if there are no log entries try running the service manually with:

    $ sudo -u postgres /usr/pgsql-9.6/bin/pg_ctl start -D /var/lib/pgsql/9.6/data

### Re-import the databases

Once the Postgres 9.6 service is running, re-import the databases:

    $ psql -U postgres -f ~/pgbackup/pg-databases.dump postgres

Then check that the QIS database has been imported correctly:

    $ psql -U postgres qis-mgmt
    psql (9.6.10)
    Type "help" for help.

    qis-mgmt=# select count(id) from images;
      count
    ---------
     1963823
    (1 row)

### Tidy up

Edit `/var/lib/pgsql/9.6/data/pg_hba.conf` and remove the temporary `trust`
access for local users so that only the "production" rules remain. Once this is
done, restart the new service:

    $ sudo service postgresql-9.6 restart

And check that the QIS application can now connect to the database and is working
correctly. A good test page is: https://images.example.com/admin/users/.
QIS keeps a pool of cached database connections, so it is normal to see a number
of "connection closed" errors before everything settles down. If the errors keep
on coming, check the QIS log file.

If all is well, vacuum and analyze the new databases (remembering to set your
PATH to use the new version, if not already done above):

    $ export PATH=/usr/pgsql-9.6/bin:$PATH
    $ sudo -u postgres vacuumdb -a -z -v

### Optional - remove the old version

Lastly, and optionally, the old Postgres package and data can be removed.

:warning: Be careful about this because it is likely that QIS's Python-Postgres
driver will still be linked to the older client libraries. If you recompile the
Python-Postgres driver (psycopg2) against the new packages, and re-install it,
then it should be safe to delete the old packages.

:warning: As noted above, THIS HAS NOT YET BEEN TESTED!

    $ sudo yum erase postgresql postgresql-server
    $ sudo rm -rf /var/lib/pgsql/data/*
    $ sudo rm -rf ~/pgbackup
