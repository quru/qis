# Upgrading QIS

Most releases only require replacement application files and a restart of the
web server:

    $ cd /opt/qis
    $ sudo -u qis tar -xvf /path/to/QIS-libs.tar.gz
    $ sudo -u qis tar --strip-components=1 -xvf /path/to/QIS-x.y.z.tar.gz
    $ sudo systemctl restart httpd

Occasionally however a more involved upgrade is required. These releases are
flagged in the [change log](changelog.md) and will be documented here.

## v4.1.4

Release 4.1.4 includes a number of changes to the Apache configuration. To
upgrade an existing configuration, use a text editor to change both of the QIS
Apache configuration files:

	$ cd /etc/httpd/conf.d/               # CentOS / Red Hat
	$ cd /etc/apache2/sites-available/    # Debian / Ubuntu
	$ vi qis.conf
	$ vi qis-ssl.conf

In the `Alias` section, add a new directory mapping for the new `.well-known` URL:

    Alias /.well-known/    /opt/qis/src/imageserver/static/.well-known/

To modernise the TLS/HTTPS configuration (disables TLS 1.0 and 1.1), change these
2 `SSL` entries to:

    SSLProtocol             all -SSLv2 -SSLv3 -TLSv1 -TLSv1.1
    SSLCipherSuite          ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256

To log clients' real IP addresses when behind a proxy server or load balancer,
change `LogFormat` to:

    LogFormat "%h %{X-Forwarded-For}i %t \"%r\" %>s %B %{X-Time-Taken}o %D %{X-From-Cache}o \"%{User-Agent}i\" \"%{Referer}i\"" imaging

To allow file uploads and API requests from browsers coming from any origin
**with a valid API token** (this is the new default), set the `Header` lines:

    # Allow other domains to query the data API (required for canvas/zoom image viewer)
    Header set Access-Control-Allow-Origin "*"
    Header set Access-Control-Allow-Headers "Origin, Authorization, If-None-Match, Cache-Control, X-Requested-With, X-Csrf-Token"
    # Allow other domains to see the returned image headers
    Header set Access-Control-Expose-Headers "Content-Length, X-From-Cache, X-Time-Taken"

## v2.x to v3.0

Version 3 supports only Python 3. There are no changes to the QIS database or
directory structure, so most of the work involves configuration changes to install
and use Python 3.

From Quru you will need the latest ImageMagick interface for your platform, which
has been re-compiled for the Python 3, e.g. `qismagick-3.0.0-cp35-cp35m-linux_x86_64.whl`.

### Ubuntu 16

Install new packages:

	$ sudo apt-get remove libapache2-mod-wsgi
	$ sudo apt-get install -y python3 libapache2-mod-wsgi-py3 python3-pip

### CentOS 7

Install the EPEL and IUS repositories:

	$ sudo yum install -y epel-release
	$ sudo yum install -y https://centos$(rpm -E '%{rhel}').iuscommunity.org/ius-release.rpm

Install new packages:

	$ sudo yum erase mod_wsgi
	$ sudo yum install -y python35u python35u-mod_wsgi python35u-pip

### Red Hat Enterprise Linux 7

Install the EPEL and IUS repositories:

	$ sudo yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-$(rpm -E '%{rhel}').noarch.rpm
	$ sudo yum install -y https://rhel$(rpm -E '%{rhel}').iuscommunity.org/ius-release.rpm

Install new packages:

	$ sudo yum erase mod_wsgi
	$ sudo yum install -y python35u python35u-mod_wsgi python35u-pip

### Upgrading

Backup the previous version (excluding images):

    $ mkdir qis-backup && cd qis-backup
    $ sudo rsync -a --exclude images /opt/qis/* .

Extract the latest files:

    $ cd /opt/qis
    $ sudo -u qis tar -xvf /path/to/QIS-libs.tar.gz
    $ sudo -u qis tar --strip-components=1 -xvf /path/to/Quru\ Image\ Server-3.0.0.tar.gz
    $ sudo -u qis pip3.5 install --prefix /opt/qis /path/to/qismagick-3.0.0-cp35-cp35m-linux_x86_64.whl

Remove the old Python 2.x libraries:

    $ cd /opt/qis
	$ sudo rm -rf lib/python2*

### Apache configuration

The older QIS configuration for Apache includes a path reference of `python2.x`
that needs updating. Rather than change this to `python3.x`, QIS v3 has a shorter
and simpler configuration that does away with the version number.

Use a text editor to change both of the QIS Apache configuration files:

	$ cd /etc/httpd/conf.d/               # CentOS / Red Hat
	$ cd /etc/apache2/sites-available/    # Debian / Ubuntu
	$ vi qis.conf
	$ vi qis-ssl.conf

In each file, change the existing `WSGIDaemonProcess` definition from having a
single `python-path` attribute:

	python-path=/opt/qis/src:/opt/qis/lib/python2.7/site-packages:/opt/qis/lib64/python2.7/site-packages

to having separate `python-home` and `python-path` attributes instead:

	python-home=/opt/qis  python-path=/opt/qis/src

Then check that the configuration changes are OK:

	$ httpd -t      # CentOS / Red Hat
	$ apache2 -t    # Debian / Ubuntu
	Syntax OK

### Restart services

Data and images cached under Python 2 cannot be loaded under Python 3, therefore
the cache needs to be reset. Apache needs to be restarted to bring in the updated
Python 3 code and modules and configuration.

	$ sudo systemctl restart memcached
	$ sudo systemctl restart httpd        # CentOS / Red Hat
	$ sudo systemctl restart apache2      # Debian / Ubuntu

If the Apache service fails to start or returns errors, check the error log
at `/var/log/httpd/error_log` or `/var/log/apache2/error.log`.

## v2.x to v2.6

This release contains a number of potentially breaking changes, though only
users of Internet Explorer 8 and below should be affected
(which in 2017 is hopefully nobody).

* Minified JavaScript file names have been renamed from the quirky format
  `foo_yc.js` to the more conventional format `foo.min.js`.
* The path to the MooTools library has changed, as this library is now only
  used internally, and is no longer required by client-side code.
* Removed the _excanvas_ library (Internet Explorer 8 canvas emulation).
* Removed the JSONP options from the image gallery and viewers;
  cross-domain API calls now use CORS instead.
* Dropped support for Internet Explorer 8 and below.

### Upgrading

For upgrading existing installations, an upgrade script has been provided to clean up
legacy files and optionally to provide compatibility with the old `foo_yc.js`
JavaScript file paths.

Backup the previous version (excluding images):

    $ export QIS_HOME=/opt/qis
    $ mkdir qis-backup && cd qis-backup
    $ sudo rsync -a $QIS_HOME/* . --exclude images

Extract the latest files:

    $ cd $QIS_HOME
    $ sudo -u qis tar --strip-components=1 -xvf /path/to/Quru\ Image\ Server-2.6.0.tar.gz

Then run the upgrade script:

    $ sudo -u qis $QIS_HOME/src/imageserver/scripts/v2.6_upgrade.sh

### Apache configuration

The removal of JSONP requires a new HTTP header to be set in Apache.
In each of the Apache configuration files:

* `/etc/httpd/conf.d/qis.conf`
* `/etc/httpd/conf.d/qis-ssl.conf`

Add the following new lines inside the main `VirtualHost` section:

    # Allow other domains to query the data API (required for canvas/zoom image viewer)
    Header set Access-Control-Allow-Origin "*"

Then reload the Apache configuration:

    $ sudo apachectl -t && sudo apachectl -k graceful

This new configuration requires Apache's `mod_headers` module to be enabled, if
it is not enabled by default.

#### robots.txt

This release allows image URLs to be indexed in the web server's `robots.txt` file.
If you do not want to allow this, copy the older version back:

    $ sudo -u qis cp /tmp/qis-backup/src/imageserver/static/robots.txt $QIS_HOME/conf/local_robots.txt

And change the 2 Apache configuration files to direct requests for `robots.txt`
across to the older file:

    Alias /robots.txt      /opt/qis/conf/local_robots.txt

## v1.50 to v2.4

This is a major upgrade that requires database changes and a data migration.
An upgrade script is supplied to automate this process where possible, but some
down-time is unfortunately required. The Memcached cache is also reset as part of
this process.

For starting versions prior to v1.50, consult the change log to see what upgrades
you also need to perform prior to this one.

### Prerequisites

Postgres 9.2 or above is now required (a release supporting the `json` data type).
Previously QIS would run on Postgres 8.x but this is no longer the case.

### Build

Follow the build instructions in the README file to build the QIS application
package and the Python library dependencies for your platform:

    Quru Image Server-2.4.0.tar.gz
    QIS-libs.tar.gz

and from Quru obtain the latest ImageMagick interface for your platform:

    qismagick-2.1.0-cp27-cp27mu-linux_x86_64.whl

### Installation and upgrade

* Back up the old `/opt/qis` directory (the `images` sub-directory can be skipped)
```
    $ mkdir qis-backup && cd qis-backup
    $ sudo rsync -a /opt/qis/* . --exclude images
```
* Copy the above build files to `/tmp`
* Stop the Apache service
* Install the v2 QIS files (standard upgrade procedure):
```
    $ sudo pip install -U pip
    $ cd /opt/qis/
    $ sudo -u qis tar --strip-components=1 -xvf /tmp/Quru\ Image\ Server-2.4.0.tar.gz
    $ sudo -u qis tar -xvf /tmp/QIS-libs.tar.gz
    $ sudo -u qis pip install --prefix /opt/qis /tmp/qismagick-2.1.0-cp27-cp27mu-linux_x86_64.whl
```
* Run the v2 upgrade script:
```
    $ cd /opt/qis/src/imageserver/scripts
    $ sudo -u qis python v2_upgrade.py
```
* Read through the `v2_upgrade.py` output carefully for advisory and error information.
  If there are any errors you can just re-run the `v2_upgrade.py` script again
  after taking remedial action.
* If your local settings file (by default `/opt/qis/conf/local_settings.py`)
  contains any of the following entries, they can now be deleted:
  * `LDAP_AUTO_CREATE_USER_ACCOUNTS`
  * `TEMPLATES_BASE_DIR`
  * `IMAGE_FORMAT_DEFAULT`
  * `IMAGE_QUALITY_DEFAULT`
  * `IMAGE_COLORSPACE_DEFAULT`
  * `IMAGE_DPI_DEFAULT`
  * `IMAGE_STRIP_DEFAULT`
  * `IMAGE_EXPIRY_TIME_DEFAULT`
* Start the Apache service
* Log in as an administrator,
  review the imported image templates,
  and check that the newly created default template contains your previous default image settings
* Test that your images are being served correctly
* If you chose not to remove your old template files during the upgrade,
  you can at a later time delete the directory:
  * `/opt/qis/templates`
