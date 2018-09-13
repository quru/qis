# QIS installation guide

To follow this guide you need to have some knowledge of Linux server administration,
and be familiar with using the command line interface and some common utilities.

If you want to read about what QIS does before installing it, read the
[application introduction and overview](overview.md).

As an alternative to manually installing everything as described here, QIS can
also be run inside Docker using the supplied Dockerfiles and
[docker-compose](../deploy/docker/docker-compose.yml) script.

## Overview

Apart from itself, QIS requires these other applications to be installed:

* Python 3
* Apache web server (plus the mod_wsgi module)
* PostgreSQL database server
* Memcached caching server

Each of these can be run on a single server or across multiple servers, and each
can be run as one application instance or many (clustered or load balanced). To
simplify this guide, one instance of each application will be installed on one server.

QIS requires a Linux-based operating system. However, development and testing takes
place on Mac OS X, so it is likely that other unix-based operating systems will also
work. For a list of operating systems that are known to work, see the
[operating systems](operating_systems.md) notes.

The examples given here assume a Fedora-based system (with the `systemd` init
system and the `yum` installer). For Debian-based systems, replace `yum` with
`apt-get`, and be aware that the commands, package names and file locations may
differ slightly. You can find an installation script for Ubuntu in the
[Dockerfiles](../deploy/docker/qis-as/Dockerfile).

The rest of this guide will take you through the installation and configuration
of QIS and the required applications on a new blank server.

## Update the operating system

First it is recommended to update the operating system as a whole, to bring in
the latest software updates and security fixes.

	$ sudo yum -y update

### On Fedora-based systems - enable additional package repositories

At the time of writing, support for Python 3 packages in CentOS 7 and Red Hat Linux 7
is disappointing. The additional EPEL and IUS repositories need to be installed in
order to provide Python 3 versions of the packages that QIS requires. No additional
repositories are required for Debian / Ubuntu 16.

On CentOS 7:

	$ sudo yum install -y epel-release
	$ sudo yum install -y https://centos$(rpm -E '%{rhel}').iuscommunity.org/ius-release.rpm

On Red Hat Enterprise Linux 7:

	$ sudo yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-$(rpm -E '%{rhel}').noarch.rpm
	$ sudo yum install -y https://rhel$(rpm -E '%{rhel}').iuscommunity.org/ius-release.rpm

## Install Memcached

Install the package:

	$ sudo yum -y install memcached

Raise the memory limit from its default 64MB to a more useful value.
Edit `/etc/sysconfig/memcached` and change `CACHESIZE`:

	CACHESIZE="1024"

When the Memcached service is full, your server must still have enough RAM free
to run the other applications (if installed) and perform caching of operating system
files, without swapping. This is an advanced topic, see the [tuning guide](tuning.md)
for more information.

By default, Memcached accepts remote connections from anywhere**. If Apache will be
installed on a different server this is fine, but you must add a firewall rule to
prevent connections from elsewhere. If Apache will be installed on the same server,
tell Memcached to accept local connections only. Edit `/etc/sysconfig/memcached` and
change `OPTIONS` as follows:

	OPTIONS="-l 127.0.0.1"

**Note that some Debian-based systems set `-l 127.0.0.1` by default in `/etc/memcached.conf`.

Set the service to start on boot and start it now:

	$ sudo systemctl enable memcached
	$ sudo systemctl start memcached

## Install Postgres

Install the package:

	$ sudo yum -y install postgresql-server

Initialise a new Postgres database collection:

	$ sudo -u postgres initdb -D /var/lib/pgsql/data --auth-host=md5 --auth-local=peer

Set the Postgres tuning options in `/var/lib/pgsql/data/postgresql.conf`.
This is an advanced topic, see the tuning guide and the
[Postgres documentation](https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server)
for more information. Typically though the following settings are updated:

* `shared_buffers` - raise to the amount of RAM you want to dedicate to Postgres
  (e.g. `512MB`)
* `effective_cache_size` - the value of `shared_buffers` plus however much server
  RAM you expect to be free after all other applications are running
* `checkpoint_segments` - set to `16`
* `checkpoint_completion_target` - set to `0.9`

If Apache will be installed on a different server, enable TCP/IP connections to
the Postgres service. This has security implications, and the example below allows
remote connections from anywhere. Consult the [Postgres documentation](https://www.postgresql.org/docs/9.2/static/auth-pg-hba-conf.html)
for more information. You can skip this step if Apache will be installed on the
same server.

	$ echo "listen_addresses = '*'" | sudo tee -a /var/lib/pgsql/data/postgresql.conf
	$ echo "host    all    all    0.0.0.0/0    md5" | sudo tee -a /var/lib/pgsql/data/pg_hba.conf

Set the service to start on boot and start it now:

	$ sudo systemctl enable postgresql
	$ sudo systemctl start postgresql

If the service fails to start, see the _Raising the system limits_ section below.
But assuming success, create a QIS database user and new empty database:

	$ sudo -u postgres psql -c "CREATE ROLE qis WITH LOGIN PASSWORD 'password'"
	$ sudo -u postgres createdb --encoding=UTF8 --locale=en_GB.UTF8 --owner=qis qis-cache
	$ sudo -u postgres createdb --encoding=UTF8 --locale=en_GB.UTF8 --owner=qis qis-mgmt

The `qis` user's password should be set to a secure value.

## Add an operating system user to run QIS

The QIS web application runs under its own local user account. This allows the
application's processes, file and directory permissions to be subject to standard
access controls.

	$ sudo useradd --comment "Quru Image Server" --home /opt/qis --system --shell /sbin/nologin qis

If you require any other web-based systems to integrate with QIS, it can be useful
to make the `qis` user a member of the `apache` group. In this case you will first
need to install the Apache package for the `apache` group to be created. The
equivalent group on a Debian-based system is `www-data`.

	$ sudo yum -y install httpd
	$ sudo useradd --groups apache --comment "Quru Image Server" --home /opt/qis --system --shell /sbin/nologin qis

## Download the QIS packages

QIS is installed from 2 package files:

* `QIS-x.y.z.tar.gz` - the main platform-independent Python web application
* `QIS-libs-x-y-z.tar.gz` - the application's Python dependencies, including compiled
  C extensions as platform-specific binaries

These can either be downloaded from the GitHub releases page:

* https://github.com/quru/qis/releases

Or if you have the development environment set up, you can build them for your
own platform by running:

	$ cd <project>
	$ make distribute

## Install QIS

Install the required operating system packages and some useful utilities:

	$ sudo yum -y install pwgen tar zip unzip python35u python35u-pip \
	                      openssl openldap libmemcached ghostscript \
	                      ImageMagick postgresql

You will next require the 2 QIS distribution files as described in the previous
section. Note that the `libs` file is specific to server architecture and Python
version, and you require the correct version for your operating system. The
following commands assume you have copied these files into the `/tmp` directory.

Create the QIS base directory and extract the files:

	$ sudo mkdir /opt/qis && sudo chown qis:qis /opt/qis
	$ cd /opt/qis
	$ sudo -u qis tar -xvf /tmp/QIS-libs-centos-7-py35-x86_64.tar.gz
	$ sudo -u qis tar --strip-components=1 -xvf /tmp/QIS-4.0.0.tar.gz

The installation should look like this:

	$ ls -l /opt/qis/
	total 40
	drwxr-xr-x.  2 qis qis    45 Feb  5 12:19 conf
	drwxr-xr-x. 10 qis qis   123 Feb  5 12:19 deploy
	drwxr-xr-x.  3 qis qis  4096 Feb  5 12:19 doc
	drwxr-xr-x.  2 qis qis  4096 Feb  5 12:19 icc
	drwxr-xr-x.  9 qis qis   109 Feb  5 12:19 images
	drwxr-xr-x.  3 qis qis    23 Feb  5 12:18 lib
	drwxr-xr-x.  2 qis qis  4096 Feb  5 12:19 licences
	drwxr-xr-x.  2 qis qis    35 Feb  5 12:19 logs
	-rw-r--r--.  1 qis qis   465 Feb  5 12:19 PKG-INFO
	-rw-r--r--.  1 qis qis 13206 Feb  5 11:19 README.md
	-rw-r--r--.  1 qis qis   547 Feb  5 12:19 setup.cfg
	-rw-r--r--.  1 qis qis  1257 Dec  5 10:19 setup.py
	drwxr-xr-x.  5 qis qis    71 Feb  5 12:19 src

## Install Apache and friends

Install the packages:

	$ sudo yum -y install httpd mod_ssl logrotate python35u-mod_wsgi

Set the language and character set (where `UTF8` is preferred) for the Apache
process by adding a few lines to the file `/etc/sysconfig/httpd`:

	LANG=en_GB.UTF-8
	LC_ALL=en_GB.UTF-8

If not enabled by default, enable the following Apache modules. The process for
this is operating system specific. At the time of writing these are all enabled
by default in CentOS/Red Hat, but need explicitly enabling in Debian/Ubuntu.

* mod_ssl
* mod_headers
* mod_expires

Create Apache configuration files to run QIS:

	$ cd /opt/qis
	$ sudo cp deploy/centos7/wsgi.conf /etc/httpd/conf.d/wsgi.conf
	$ sudo cp deploy/centos7/httpd.conf.sample /etc/httpd/conf.d/qis.conf
	$ sudo cp deploy/centos7/httpd-ssl.conf.sample /etc/httpd/conf.d/qis-ssl.conf

Substituting `centos7` for the directory name in `/opt/qis/deploy` that most closely
matches your operating system. Ubuntu 16 and CentOS 7 ship with Apache v2.4, while
CentOS 6 ships with Apache v2.2. The two Apache versions have rather different
configuration files.

Customise the `qis.conf` (HTTP service) and `qis-ssl.conf` (HTTPS service) files
for your server. The following entries will need to be changed:

* `ServerName` - set this to be the host name (including domain name) of your server
* `WSGIDaemonProcess` - set the total number of processes (i.e. in both `conf` files)
  to be roughly the number of CPU cores in your server, minus 1 if Postgres is also
  installed, minus 1 if Memcached is also installed. If in doubt, start small and
  leave the default value of `2`.

You can review that the other default settings meet your needs, then check the
validity of the new `conf` files:

	$ httpd -t
	Syntax OK

You may also need to adjust the default Apache settings in `/etc/httpd/conf/httpd.conf`,
e.g. to raise the maximum number of workers. This is an advanced topic, see the tuning guide
and the [Apache documentation](https://httpd.apache.org/docs/current/misc/perf-tuning.html)
(especially the MPM settings) for more information. A guideline for the number of Apache
workers required is 4 * `WSGIDaemonProcess` processes * `WSGIDaemonProcess` threads.
By default, Apache has worker limit of around 250.

Set the Apache service to start on boot. We'll start the service in this session after
performing the QIS configuration that follows below.

	$ sudo systemctl enable httpd

### Optional - HTTPS configuration

The `qis-ssl.conf` file enables HTTPS in Apache using the server's default TLS
certificate files. This arrangement does work, but will give nasty security warnings
in most web browsers, and will require you to "add a security exception" or similar.

To avoid these security warnings, you will need certificate files that are specific
to the host name (domain name) of your server. You can buy TLS certificates from
companies such as [Thawte](https://www.thawte.com/), or obtain them free from
[Let's Encrypt](https://letsencrypt.org/).

Installation instructions are provided by the certificate suppliers, but generally
involve copying the files onto your server and setting the locations to them in the
file `/etc/httpd/conf.d/qis-ssl.conf`.

### Optional - Set the cross-domain policy

Web browsers allow images, JavaScript and CSS files to be loaded from any domain.
Background data requests however are only allowed to be made to the same domain as
the originating web page by default. The zooming image viewer, slideshow/carousel
and gallery viewers all make background data requests. Therefore to enable the use
of these viewers (and the required public data APIs) on any web site, QIS sets the
following HTTP header in `qis.conf` and `qis-ssl.conf`:

    Header set Access-Control-Allow-Origin "*"

If you want to lock down this data access to a single domain, change the `*` value as
[described here](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Allow-Origin).

### Optional - Logrotate configuration

The default Apache configuration (in `/etc/httpd/conf.d/qis.conf` and
`/etc/httpd/conf.d/qis-ssl.conf`) logs every image request to an Apache _access log_ file
in the `/var/log/httpd/` directory. The _logrotate_ utility (we installed above) is then
responsible for closing each log file and starting a new one. By default it does this once
per week, which is fine for a small to medium traffic web site, but a very busy site might
accumulate 1GB of logs per day.

If you have a very busy image server, you can instead swap the log files on a daily basis,
and also compress the archived logs to save disk space.

View the current logrotate configuration for Apache with:

	$ cat /etc/logrotate.d/httpd
	/var/log/httpd/*log {
	    missingok
	    notifempty
	    sharedscripts
	    delaycompress
	    postrotate
	        /bin/systemctl reload httpd.service > /dev/null 2>/dev/null || true
	    endscript
	}

To enable log compression, archive daily, and keep 7 days worth of logs, add the
`compress`, `daily`, and `rotate` directives so that the configuration becomes:

	/var/log/httpd/*log {
	    missingok
	    notifempty
	    sharedscripts
	    compress
	    delaycompress
	    daily
	    rotate 7
	    postrotate
	        /bin/systemctl reload httpd.service > /dev/null 2>/dev/null || true
	    endscript
	}

## Optional - Raising the system limits

Some Linux-based systems default to a low limit on the number of running processes
(including threads) and files (including network connections), which can cause
"resource temporarily unavailable" errors on a busy web server. To check these limits,
run:

	$ ulimit -n -u
	open files                      (-n) 1024
	max user processes              (-u) 1024

Values like these should be raised.

### With systemd

On systems such as CentOS 7 that use systemd, system limits are controlled
at the service level. Do not edit the main service file, instead install a
service override file to raise the limits:

    $ sudo mkdir /etc/systemd/system/httpd.service.d
    $ cd /opt/qis
    $ sudo cp deploy/centos7/httpd-limits.conf /etc/systemd/system/httpd.service.d/limits.conf
    $ sudo systemctl daemon-reload
    $ sudo systemctl restart httpd.service

### Without systemd

On older systems such as CentOS 6, system limits are defined at the user level.
To raise the limits, install a configuration file into `/etc/security/limits.d/`:

    $ cd /opt/qis
    $ sudo cp deploy/centos6/limits.conf /etc/security/limits.d/qis.conf
    $ sudo service httpd restart

### Postgres

Postgres versions below 9.4 allocate a block of memory on startup that may
exceed the system's "shared memory" limit. If the Postgres service fails to start,
check the log file at `/var/lib/pgsql/data/pg_log/postgresql.log`. If there is an
error regarding shared memory, you will need to raise the shared memory limits.

To raise the shared memory limit to 16GB, run commands:

	$ sysctl -w kernel.shmmax=17179869184
	$ sysctl -w kernel.shmall=4194304

Then change (or add) the same values in `/etc/sysctl.conf`.
You can also refer to the [Postgres documentation](https://www.postgresql.org/docs/9.2/static/kernel-resources.html).

Postgres from version 9.4 onwards uses a different mechanism that avoids this
problem.

## Configuring the firewall

If your system has a firewall enabled, you will need to allow web traffic to
reach the server. How to do this is operating system specific. With `firewalld`
(Fedora 15+, CentOS 7+), run:

    $ sudo firewall-cmd --zone=public --permanent --add-service=http
    $ sudo firewall-cmd --zone=public --permanent --add-service=https
    $ sudo firewall-cmd --reload

With `ufw` (Ubuntu), run:

    $ sudo ufw allow http
    $ sudo ufw allow https

## Configuring Security Enhanced Linux (SELinux)

If your operating system has SELinux enabled, you must define some additional
disk permissions and install a policy file to allow the software components to
communicate with each other.

You can check this with `sestatus`:

	$ sestatus
	SELinux status:                 enabled
	SELinuxfs mount:                /sys/fs/selinux
	SELinux root directory:         /etc/selinux
	Loaded policy name:             targeted
	Current mode:                   enforcing
	Mode from config file:          enforcing
	Policy MLS status:              enabled
	Policy deny_unknown status:     allowed
	Max kernel policy version:      29

If the SELinux status is `disabled` or the current mode is not `enforcing`,
you can skip the rest of this section.

Otherwise, see if the `semanage` command is available, and if not install it:
 
	$ sudo yum install -y policycoreutils-python

Install the QIS security policy, and allow the Apache service to write to the
QIS logs and images directories:

	$ sudo semodule --install=/opt/qis/deploy/centos7/qis.pp
	$ sudo semanage fcontext --add --type httpd_log_t "/opt/qis/logs(/.*)?"
	$ sudo semanage fcontext --add --type httpd_user_rw_content_t "/opt/qis/images(/.*)?"
	$ sudo restorecon -rv /opt/qis

If you are using NFS (network file system) to access your image directories,
you will also need to run:

	$ sudo setsebool -P httpd_use_nfs on

If you installed a TLS/SSL certificate for HTTPS support, reset the security
context of the new files (set the directory names here for where you installed
the `crt/pem/key` files):

    $ sudo restorecon -rv /etc/ssl/certs/
	or
    $ sudo restorecon -rv /etc/pki/tls/

If you will be taking your QIS user accounts from an LDAP service you will need:

	$ sudo setsebool -P httpd_can_connect_ldap on

## Configuring QIS

QIS has a large number of configuration settings, but you only need to set a few
to get going. One of these is the `SECRET_KEY` value, which as the name suggests,
should be a value unique to your site and must be kept a secret. You can generate
a secret key with the `pwgen` utility:

	$ pwgen -s 32 1
	zOWp8lBL1IMVEl9uWzPn2PD2ddtZTPRv

Create a new text file `/opt/qis/conf/local_settings.py` and add these lines:

	PUBLIC_HOST_NAME = "images.example.com"
	SECRET_KEY = "zOWp8lBL1IMVEl9uWzPn2PD2ddtZTPRv"

Where the host name is the same value you used when setting up Apache, and the
secret key the value you just generated. If you want to run multiple web servers
(e.g. behind a load balancer) then these settings need to be the same on every
instance.

If you will be using a load balancer, or running your web server behind a reverse
proxy, you need to define how many intermediaries there are (usually `1`):

	PROXY_SERVERS = 1

If Memcached and Postgres are installed on the same server, you can now skip to the
_First run_ section.

Or if Memcached is on a different server, you'll need to override the default value
for the `MEMCACHED_SERVERS` setting. To the `/opt/qis/conf/local_settings.py` file,
add:

	MEMCACHED_SERVERS = ["mc.example.com:11211"]

Where `mc.example.com` is the local host name or IP address of your Memcached
server, and `11211` is the Memcached port. For multiple Memcached servers, use a
comma separated list such as `["11.22.33.44:11211", "11.22.33.45:11211"]`.

If Postgres is on a different server, you'll need to override the default values
for the 2 `DATABASE_CONNECTION` settings. To the `/opt/qis/conf/local_settings.py`
file, add:

	CACHE_DATABASE_CONNECTION = "postgresql+psycopg2://qis:password@db.example.com:5432/qis-cache"
	MGMT_DATABASE_CONNECTION = "postgresql+psycopg2://qis:password@db.example.com:5432/qis-mgmt"

Where `qis:password` is the database username and password (as set in the
_Install Postgres_ section), `db.example.com` is the local host name or IP address
of your Postgres server, and `5432` is the Postgres service port.

To review the full list of settings and their default values, view the contents
of the file `/opt/qis/src/imageserver/conf/base_settings.py`. You can override
any of these settings in your `local_settings.py` file. Do not edit
`base_settings.py` directly because this file will be overwritten the next time
you upgrade QIS.

If you are using SELinux, reset the security context of the new settings file:

    $ sudo restorecon -rv /opt/qis

## First run

The Memcached and Postgres services must already be running. Then to start QIS,
start the Apache service:

	$ sudo systemctl start httpd

and check the QIS log file to see what happened:

	$ cat /opt/qis/logs/qis.log
	2015-05-22 10:37:54,054 qis_18     INFO     Quru Image Server v4.0.0 engine startup
	2015-05-22 10:37:54,054 qis_18     INFO     Using settings base_settings + local_settings.py
	2015-05-22 10:37:54,058 qis_18     INFO     Cache usage currently 0 out of 1048576000 bytes (0%), holding 0 objects.
	2015-05-22 10:37:54,054 qis_19     INFO     Quru Image Server v4.0.0 engine startup
	2015-05-22 10:37:54,055 qis_19     INFO     Using settings base_settings + local_settings.py
	2015-05-22 10:37:54,071 qis_19     INFO     Cache usage currently 0 out of 1048576000 bytes (0%), holding 0 objects.
	2015-05-22 10:37:54,309 qis_19     INFO     Cache control database created.
	2015-05-22 10:37:54,314 qis_19     INFO     Cache control database opened.
	2015-05-22 10:37:56,221 qis_19     INFO     Created new group 'Public'
	2015-05-22 10:37:56,222 qis_19     INFO     Created Public group
	2015-05-22 10:37:56,232 qis_19     INFO     Created new group 'Normal users'
	2015-05-22 10:37:56,233 qis_19     INFO     Created Normal users group
	2015-05-22 10:37:56,243 qis_19     INFO     Created new group 'Administrators'
	2015-05-22 10:37:56,244 qis_19     INFO     Created Administrators group
	2015-05-22 10:37:56,266 qis_19     INFO     Created new user account for username 'admin' with ID 1
	2015-05-22 10:37:56,267 qis_19     INFO     Created default admin user with password SHhUxIykPH
	2015-05-22 10:37:56,278 qis_19     INFO     Created new folder for path: /
	2015-05-22 10:37:56,278 qis_19     INFO     Created root folder
	2015-05-22 10:37:56,353 qis_19     INFO     Created default folder permissions
	2015-05-22 10:37:56,364 qis_19     INFO     Management + stats database opened
	2015-05-22 10:37:56,365 qis_19     INFO     Housekeeping task scheduler started
	2015-05-22 10:37:56,388 qis_19     INFO     Loaded imaging library: ImageMagick version: 688, Ghostscript delegate: 9.14
	2015-05-22 10:37:57,514 qis_18     INFO     Cache control database opened.
	2015-05-22 10:37:57,562 qis_18     INFO     Management + stats database opened
	2015-05-22 10:37:57,562 qis_18     INFO     Housekeeping task scheduler started
	2015-05-22 10:37:57,573 qis_18     INFO     Loaded imaging library: ImageMagick version: 688, Ghostscript delegate: 9.14

A user account for the `admin` user is created the first time you start QIS.
Note down the `admin` user's password, so `SHhUxIykPH` in this example.

You can see 2 sets of log entries here, one for process ID `18` and one for process
`19`. Each of these represents one `WSGIDaemonProcess` process (see the _Install Apache_
section). With the default configuration of 2 processes serving HTTP  and 2 serving
HTTPS, you would therefore expect to see 4 processes starting here and 4 sets of
log entries.

Next, bring up the web interface and change the password for the `admin` user.

* In a web browser, navigate to `https://images.example.com/login/`
  (replacing the example host name with your own)
* Enter `admin` for the username
* Enter the password you noted from the log above
* Click _Sign in_
* Once logged in, hover over the _Administrator_ name in the top right corner, and choose _Edit account_
* In the _Password_ field, enter a new password
* Repeat the new password in the _Password confirmation_ field
* Click _Apply_

By default, both public and logged-in users have permission to view all images,
but not to upload or change them. If you want to review or change this:

* Sign in as above
* Select the _Administration_ option in the top right menu, and choose _Folder permissions_
* Choose a folder and group combination, e.g. "Root folder" and "Public"
  * The root folder permissions are inherited by all other folders (unless overridden)
  * The _Public_ group represents public / anonymous / not-logged-in users
  * The _Normal users_ group is the default group for logged in users
* The current permissions are shown
* Click _Change_ to alter the current permission level
  * Each higher permission level includes the levels that precede it
* Click _Apply_ to save your changes

Note: global permissions flags (irrespective of folder) can also be defined at the
group level in _Groups_ administration.

Your QIS installation is now complete. For more information about access permissions
and other topics you can read the [application overview](overview.md).

## Troubleshooting

You can usually find an error message (and hopefully a useful one) by looking
at one of the various log files.

* If SELinux is enabled, check for any denied operations in `/var/log/audit/audit.log`,
  and see the `audit2allow` tool for a route to fixing these
* If Postgres did not install correctly, check `/var/lib/pgsql/pgstartup.log`
  for a copy of the installation messages
* If Postgres will not start, check `/var/lib/pgsql/data/pg_log/postgresql.log`
  for most startup and runtime errors
* If Apache will not start, check `/var/log/httpd/error_log`
* If Apache is started but you cannot reach the QIS home page (`http://images.example.com/`),
  also check the Apache `error_log`
* If QIS runs in HTTP but not HTTPS, also check the Apache `error_log`
* For any other problem, check `/opt/qis/logs/qis.log` and the Apache `error_log`

## Upgrading to the Premium Edition

QIS can be upgraded to the Premium Edition with its enhanced imaging engine by
[contacting Quru](https://quru.com/qis/). We will send you an extra file compiled
for your operating system and platform, which you can install by running:

	$ sudo -u qis pip3 install --prefix /opt/qis qismagick-4.0.0-cp35-cp35m-linux_x86_64.whl
	$ sudo systemctl restart httpd.service
