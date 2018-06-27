# Quru Image Server - dynamic imaging for web and print

QIS is a high performance web server for creating and delivering dynamic images.
It is ideal for use in conjunction with your existing web site, for applications
such as image galleries and product catalogues. Some of the application features
are listed below, but for more information you can also read the
[application introduction and overview](doc/overview.md).

Quru has been using QIS in production since 2012, and the source code of the
Standard Edition is made available here under the
[Affero GPL license](https://www.gnu.org/licenses/why-affero-gpl.en.html).

Quru also offers a Premium Edition of QIS. This consists of a more fully featured
image processing engine, plus the option of obtaining professional services and
commercial support, for a modestly priced annual subscription.

## An example - HTML5 responsive images

With QIS it is a breeze to serve HTML5 [responsive images](https://responsiveimages.org/)
without having to manually resize or store multiple copies of the same image.

First we upload a single high resolution image `africa_dxm.png`.  
With different URLs we can then request scaled and cropped versions of the original:

![Earth small](doc/images/nasa_africa_300.jpg)
![Earth smaller](doc/images/nasa_africa_200.jpg)
![Earth tiny crop](doc/images/nasa_africa_100_c.jpg)

and with a snippet of HTML we can ask the web browser to download whichever
*one* of these is most appropriate for the screen size for the device (desktop,
tablet, or phone):

	<div style="width:33%">
	<img src="https://images.quru.com/image?src=nasa/africa_dxm.png&format=jpg&width=500"
	     alt="NASA picture of planet Earth"
	     srcset="https://images.quru.com/image?src=nasa/africa_dxm.png&format=jpg&width=300 300w,
	             https://images.quru.com/image?src=nasa/africa_dxm.png&format=jpg&width=200 200w,
	             https://images.quru.com/image?src=nasa/africa_dxm.png&format=jpg&width=100&left=0.15&top=0.15&right=0.7&bottom=0.7 100w"
	     sizes="33vw" />
	</div>

You might notice we have also converted the image from `png` to `jpg` format,
to achieve smaller file sizes. These scaled images are automatically created
on-demand, and are then stored in a memory cache so that they are instantly
available next time around. The original image file is stored in a directory
on the server and is never modified.

## Features

Dynamic image operations include:

* Resize, rotate, flip, crop, and tiling
* Conversion to different image formats
* Stripping of image metadata to minimise image file sizes
* Blur and sharpen (Premium Edition)
* Overlays / watermarks (Premium Edition)
* Colorspace conversion (Premium Edition)
* ICC / ICM colour profiles for print publishing (Premium Edition)
* PDF conversion to and from images (Premium Edition)

See the [imaging user's guide](doc/image_help.md) for a full list,
or try the [online demo](https://images.quru.com/demo/).

Image presentation features include:

* Bookmarkable image URLs
* Image thumbnail generation
* HTML/JavaScript libraries
  * Dependency-free with support for Internet Explorer 9 and newer
  * Animated image zooming for HTML5-compliant web browsers and tablets
  * Full-screen image viewing
  * Image carousel / slideshow
  * Image gallery / folder viewer
  * Lazily-loaded images
* Image publishing wizard with dynamic preview
* Access control via user-groups and folders

Programmatic features include:

* Image generation templates (a named group of image operations)
* Create image collections that can be viewed together or downloaded as a zip file
* A REST API that allows you to securely upload images, generate dynamic images,
  and perform management and administration

See the [API user's guide](doc/api_help.md) for more detail.

Management features in the web interface include:

* File system and image browser
  * Add, rename, move, and delete image files and folders
* User and group administration
* Folder-based access control, user permissions administration
* System reports
  * Most popular images (by number of requests, bandwidth, processing time)
  * Server performance charts

## Screenshots

JavaScript library - image gallery (incorporating zooming viewer)  
![Embeddable gallery component](doc/images/mgmt_gallery_800.jpg)

Web interface - folder browse - list view  
![Folder browse](doc/images/mgmt_folder_browse_800.jpg)

Web interface - folder browse - thumbnail view  
![Folder browse](doc/images/mgmt_folder_grid_800.jpg)

Web interface - image details  
![Image details view](doc/images/mgmt_image_view_800.jpg)

Web interface - image publishing  
![Image publisher](doc/images/mgmt_publish_800.jpg)

## Architecture

QIS depends on the following open source tools and applications:

* Linux operating system
* Python 3.4 or above - to run the QIS application code
* Apache 2.4 - the web server
* mod_wsgi Apache module - to run the QIS Python application inside Apache
* Memcached - for caching generated images and frequently accessed data
* PostgreSQL 9.2 or above - to store image and folder data, users, groups,
  folder permissions and statistics

And additionally for the Premium Edition:

* ImageMagick - image processing library
* Ghostscript - PDF processing library

For how these should be installed and configured,
see the [install guide](doc/install.md) and the [tuning guide](doc/tuning.md).

For low or predictable loads, you can install all of these on one server. QIS
in production has served 5 million images per day from a single server, albeit
a fairly powerful one (8 cores and 32GB RAM, mostly scaling and cropping digital
camera photographs, with 90% of requests served from cache).

For high or variable loads, you may want to separate out the system into web and
storage tiers. Web servers scale better as multiple small servers (rather than
one large server), and image processing is typically CPU intensive, therefore it
is primarily the web tier that should be scaled out. As an example:

![Example web and storage tiers](doc/images/arch_scaling.jpg)

This system can be scaled up and down on-demand (elastic scaling) by adding or
removing web servers at any time. Memcached can run either on a separate server
if the network is fast, on one "primary" web server, or configured as a cluster
across all the permanent web servers. QIS enables
[consistent hashing](https://en.wikipedia.org/wiki/Consistent_hashing) when
using a Memcached cluster, but you should avoid adding/removing servers to/from
the cluster because of the re-distribution of keys that will occur.

The storage tier is harder to scale. Although in general QIS does not use the
PostgreSQL database heavily, storing the Postgres data files on a fast disk
or SSD is advantageous. The v9.x releases of Postgres have seen some significant
performance improvements, so always use the latest version available. PostgreSQL
can also be clustered and replicated.

## Installation

### Deploying to a server

See the [install guide](doc/install.md) for how to deploy QIS from a release on GitHub.

### Running in Docker

For a much simpler deployment, QIS can be deployed on Docker. There is a `docker-compose`
script that will set up and run almost everything for you. The only extra setup required
is a volume on the host in which to store the persistent data, and a couple of
environment variables.

If you are familiar with Docker commands, see the
[docker-compose](deploy/docker/docker-compose.yml) script and the
[application server image notes](deploy/docker/qis-as/README.md) for more information.

## Development

To run QIS in a development environment, you will need a Memcached and a PostgreSQL
service, Python 3.4 or above, and the Python development tools `pip`, `wheel`, and
`virtualenv`. Development is possible on Linux or on Mac OS X.

### Operating system packages

See the [install guide](doc/install.md) for the operating system packages needed.

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

In the `conf` folder, create a file `local_settings.py` and add your local settings:

    # Set the project directory
    INSTALL_DIR = "/Users/matt/development/qis/"

    DOCS_BASE_DIR = INSTALL_DIR + "doc/"
    ICC_BASE_DIR = INSTALL_DIR + "icc/"
    IMAGES_BASE_DIR = INSTALL_DIR + "images/"
    LOGGING_BASE_DIR = INSTALL_DIR + "logs/"

    # Don't require HTTPS when developing
    INTERNAL_BROWSING_SSL = False
    SESSION_COOKIE_SECURE = INTERNAL_BROWSING_SSL

    # Don't collect anonymous usage stats
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
  `python -c 'import os; print(os.urandom(16))'`. You must change this value and
  keep it secret when running in production.
* `MEMCACHED_SERVERS` is a list of Memcached servers to use,
  usually only 1 in development
* `CACHE_DATABASE_CONNECTION` and `MGMT_DATABASE_CONNECTION` provide the Postgres
  usernames and passwords (`pguser:pgpwd` above), service host name and port, and
  database name
  * If Postgres is running locally and authentication is `trust` you can specify
    just the database name: `postgresql+psycopg2:///qis-mgmt`

To see the default values for these settings and the other settings that you can
override, see the [default settings file](src/imageserver/conf/base_settings.py).

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

With these files prepared you should then follow the [install guide](doc/install.md).

## Important recent changes

QIS v3 is a port of QIS v2.7 to run on Python 3 only. It contains a few tidy-ups,
slightly better performance thanks to improvements in Python 3, but otherwise adds
no major new features.

QIS v4 is the first release to be fully open source. It adds an image processing
module built on the [Pillow](https://github.com/python-pillow/Pillow) library and
becomes the new QIS Standard Edition. An optional more fully featured image processing
module, built on the ImageMagick package, is [available from Quru](https://quru.com/qis/)
and becomes QIS Premium Edition.

## Standard and Premium editions

The fully open source Standard Edition uses the Python-Pillow imaging library,
which is well suited to basic image resizing and cropping, and offers good
performance when colour accuracy is not critical (see the
[`IMAGE_RESIZE_GAMMA_CORRECT`](doc/tuning.md#pillow) setting) and when only
support for the most common file types is required.

The optional [upgrade to the Premium Edition](https://quru.com/qis/) swaps Pillow
for a proprietary interface to the ImageMagick, Ghostscript and LibRaw packages,
bringing these advantages:

* Support for image conversion to and from PDF files
* Support for reading various digital camera RAW file formats
* Support for applying ICC / ICM colour profiles
* Support for additional file types, such as PSD and SVG**
* 16 bits per pixel colour processing (instead of 8)**,
  giving more accurate colour conversions and avoiding clipping
* Better retention of file metadata, such as EXIF and TIFF tags
* Gamma corrected resizing with a minimal performance difference
* Eligibility for professional services and commercial support from Quru

** Depending on the installed version of ImageMagick, but typically enabled
by default

## Roadmap

Topics under consideration for future versions:

* Image portfolios user interface
  * Addition of "add to basket" while image browsing in the admin interface
  * Addition of portfolios administration to the admin interface
  * Portfolio publishing (to zip) from the admin interface
  * Viewing a portfolio from the gallery and slideshow viewers
* Improve the image generation architecture for more consistent performance under load
* Optional long image URL to tiny URL conversion
  * New checkbox in the image publisher
  * Add to REST API
  * Tiny URL admin pages in the web interface
* Prevent certain image attributes (width, height, overlay) from being overridden
* Image search and search results
* Image tags
  * System-defined e.g. assignment of an image category
  * User-defined
  * Tagging a zone or location on an image
  * Searching by tag
* Modernise the public JavaScript APIs / viewers
  * Use HTML5 `data-` attributes for automatic initialisation
  * Reduce the number of included files
* The ability to use an object store (e.g. Amazon S3) for back-end image storage
* New imaging operations
  * Automatic crop to target dimensions
  * Generate image frames from video files (like Gifify)
  * Enhanced EXIF / XMP support e.g. to set copyright text
  * Automatic file size optimisation (like PNG Crush)
* Support for new image formats
  * BPG, JPEG XR, WEBP
  * HDRI, wide colour / Display P3 color spaces
* Cloud storage integration (Dropbox, Google Drive, ...)
* Social media integration (Instagram, Flickr, Pinterest, ...)
