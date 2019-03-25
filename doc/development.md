## Developing QIS

To run QIS in a development environment, you will need a Memcached and a PostgreSQL
service, Python 3.4 or above, and the Python development tools `pip`, `wheel`, and
`virtualenv`. Development is possible on Linux or on Mac OS X.

### Operating system packages

See the [install guide](install.md) for the operating system packages needed.

The following development packages (here on a Fedora-based system) are also
required in order to build and install the application's Python dependencies:

	$ sudo yum install -y gcc gcc-c++ git curl wget make tar zip unzip which \
	                   java-1.8.0-openjdk-headless \
	                   postgresql-devel openldap-devel openssl-devel libmemcached-devel \
	                   python35u-devel python35u-pip

### Starting development

Get the code, create a Python 3 virtualenv and install the Python dependencies:

	$ git clone https://github.com/quru/qis.git
	$ cd qis
	$ make venv

Create 2 empty Postgres databases, `qis-cache` and `qis-mgmt`.

In the project's `conf` folder, create a file `local_settings.py` and add your
local settings:

    # Set the project directory
    INSTALL_DIR = "/Users/matt/development/qis/"

    DOCS_BASE_DIR = INSTALL_DIR + "doc/"
    ICC_BASE_DIR = INSTALL_DIR + "icc/"
    IMAGES_BASE_DIR = INSTALL_DIR + "images/"
    LOGGING_BASE_DIR = INSTALL_DIR + "logs/"

    # Don't require HTTPS when developing
    INTERNAL_BROWSING_SSL = False
    SESSION_COOKIE_SECURE = INTERNAL_BROWSING_SSL

    # Don't send anonymous usage stats in development
    USAGE_DATA_URL = ""

    # Use random bytes for the session secret key (and change this value in production!)
    SECRET_KEY = b'>8F\xa7\xeab\x1f\x85\xc8\xc0\xab\xfd-\xb0\x85T'

    # Connection address of the Memcached service
    MEMCACHED_SERVERS = ["localhost:11211"]

    # Connection address and login credentials for the Postgres databases
    CACHE_DATABASE_CONNECTION = "postgresql+psycopg2://pguser:pgpwd@localhost:5432/qis-cache"
    MGMT_DATABASE_CONNECTION = "postgresql+psycopg2://pguser:pgpwd@localhost:5432/qis-mgmt"

Where:

* `INSTALL_DIR` is the full path to the project directory on your machine
* `SECRET_KEY` is a random value that you can generate by running
  `python3 -c 'import os; print(os.urandom(16))'`. You must change this value and
  keep it secret when running in production.
* `MEMCACHED_SERVERS` is a list of Memcached servers to use,
  usually only 1 in development
* `CACHE_DATABASE_CONNECTION` and `MGMT_DATABASE_CONNECTION` provide the Postgres
  usernames and passwords (`pguser:pgpwd` above), service host name and port, and
  database name
  * If Postgres is running locally and authentication is `trust` you can specify
    just the database name: `postgresql+psycopg2:///qis-mgmt`

To see the default values for these settings and the other settings that you can
override, see the [default settings file](../src/imageserver/conf/base_settings.py).

### Running the development server

To run the development server in debug mode with verbose logging, run:

    $ make runserver
    ...
    [checks/installs Python libraries]
    ...
    * Serving Flask app "imageserver.flask_app" (lazy loading)
    * Environment: development
    * Debug mode: on
    * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
    * Restarting with stat
    2018-06-25 17:10:29,831 qis_76290  INFO     Quru Image Server v4.0.0 engine startup
    2018-06-25 17:10:29,834 qis_76290  INFO     Using settings base_settings + local_settings.py
    2018-06-25 17:10:29,834 qis_76290  INFO     *** Debug mode ENABLED ***
    2018-06-25 17:10:29,879 qis_76290  INFO     Cache control database opened.
    2018-06-25 17:10:29,970 qis_76290  INFO     Management + stats database opened
    2018-06-25 17:10:29,970 qis_76290  INFO     Housekeeping task scheduler started
    2018-06-25 17:10:30,019 qis_76290  INFO     Loaded imaging library: Pillow version: 5.1.0

On first run, the required database tables and default data will be created
automatically. Watch the output for the creation of the `admin` user account,
and make a note of the password. If you miss the output, you can also find the
`admin` user account details in `logs/qis.log`.

In debug mode, the development server restarts automatically when you save a change
to a Python file. The un-minified versions of JavaScript files are served up,
and you can edit the JavaScript files and just refresh your browser to bring in
the changes. When your changes are complete, to minify the JavaScript files for
deployment, run:

    $ make webpack

To simulate a production environment and run the development server without debug
mode, run:

    $ export FLASK_ENV=production
    $ make runserver
    ...
    [checks/installs Python libraries]
    ...
    * Serving Flask app "imageserver.flask_app" (lazy loading)
    * Environment: production
      WARNING: Do not use the development server in a production environment.
      Use a production WSGI server instead.
    * Debug mode: off
    * Running on http://0.0.0.0:5000/ (Press CTRL+C to quit)

### Running the tests

The application has a fairly large test suite that can be run to check that new
changes have not broken something. It takes several minutes to complete.

To run the tests, ensure that Memcached is running and the development server
stopped, then run:

    $ make test
    ...
    [testing output]
    ...
    Stats server shutdown
    Logging server shutdown
    Task server shutdown
    ----------------------------------------------------------------------
    Ran 251 tests in 386.572s
    OK

In the past some tests have been rather fragile, and some are affected e.g. by
the particular version of image libraries installed. This situation has improved
and hopefully will continue to improve over time.

### Building the QIS packages

To run QIS in production, you will need files:

* `QIS-4.x.x.tar.gz` - the main QIS Python web application
* `QIS-libs.tar.gz` - the application's Python dependencies,
  including compiled C extensions as platform-specific binaries

To generate these files from the development project, run:

    $ make distribute
    ...
    [build script output]
    ...
    $ ls -l dist/
    -rw-r--r--  1 matt  staff  56083009 27 Jun 11:08 QIS-4.0.0.tar.gz
    -rw-r--r--  1 matt  staff   9450227 27 Jun 11:08 QIS-libs.tar.gz

With these files prepared you should then follow the [install guide](install.md).
