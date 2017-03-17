# Upgrading QIS

Most releases only require replacement application files and a restart of the
web server, as described in the [change log](changelog.md). Occasionally however
a more involved upgrade is required; these releases will be documented here.

## v1.50 to v2.4.0

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
	dependencies.tar.gz

and from Quru obtain the latest ImageMagick interface for your platform:

	qismagick-2.1.0-cp27-cp27mu-linux_x86_64.whl

### Installation and upgrade

* Back up the old `/opt/qis` directory (the `images` sub-directory can be skipped)
* Copy the above build files to `/tmp`
* Stop the Apache service
* Install the v2 QIS files (standard upgrade procedure):

	$ sudo pip install -U pip
	$ cd /opt/qis/
	$ sudo -u qis tar --strip-components=1 -xvf /tmp/Quru\ Image\ Server-2.4.0.tar.gz
	$ cd lib/python2.7
	$ sudo -u qis tar -xvf /tmp/dependencies.tar.gz
	$ cd ../..
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