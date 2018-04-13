# Upgrading QIS

Most releases only require replacement application files and a restart of the
web server, as described in the [change log](changelog.md). Occasionally however
a more involved upgrade is required; these releases will be documented here.

## v2.x to v3.0

Version 3 supports only Python 3. There are no changes to the QIS database or
directory structure, so most of the work involves configuration changes to install
and use Python 3.

From Quru you will need the latest ImageMagick interface for your platform, which
has been re-compiled for the Python 3, e.g. `qismagick-3.0.0-cp35-cp35m-linux_x86_64.whl`.

### Ubuntu 16

Install new packages:

	$ sudp apt-get remove libapache2-mod-wsgi
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
    $ sudo -u qis pip3 install --prefix /opt/qis /path/to/qismagick-3.0.0-cp35-cp35m-linux_x86_64.whl

Remove the old Python 2.x libraries:

    $ cd /opt/qis
	$ sudo rm -rf lib/python2*

Update the Apache configuration to change `python2.x` directory paths to `python3.x`,
test the Apache configuration and restart Apache.

On CentOS/RHEL:

	$ sudo sed -i -e 's|python2.7|python3.5|g' /etc/httpd/conf.d/*qis*
    $ sudo apachectl -t && sudo systemctl restart httpd

On Ubuntu:

	$ sudo sed -i -e 's|python2.7|python3.5|g' /etc/apache2/sites-available/*qis*
    $ sudo apachectl -t && sudo systemctl restart apache2

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

    $ mkdir qis-backup && cd qis-backup
    $ sudo rsync -a /opt/qis/* . --exclude images

* Copy the above build files to `/tmp`
* Stop the Apache service
* Install the v2 QIS files (standard upgrade procedure):

    $ sudo pip install -U pip
    $ cd /opt/qis/
    $ sudo -u qis tar --strip-components=1 -xvf /tmp/Quru\ Image\ Server-2.4.0.tar.gz
    $ sudo -u qis tar -xvf /tmp/QIS-libs.tar.gz
    $ sudo -u qis pip install --prefix /opt/qis /tmp/qismagick-2.1.0-cp27-cp27mu-linux_x86_64.whl

* Run the v2 upgrade script:

    $ cd /opt/qis/src/imageserver/scripts
    $ sudo -u qis python v2_upgrade.py

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
