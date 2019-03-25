# QIS application dependencies

### Postgres

* PostgreSQL 9.2 or above (due to use of JSON data type)

### Memory cache

* Memcached 1.2.8 or above
* libmemcached 1.0.10 / 1.0.16 (0.32 or above is required)
    * 1.0.8 shipping in Ubuntu 14.04.3 has a set_socket_options() bug
      https://bugs.launchpad.net/libmemcached/+bug/1021819
* Membase 1.7.1 (note: Membase support is untested since 2011)

### Web server

* Apache 2.2.17 or above
* mod_wsgi 3.2.7 or above

### LDAP authentication

* OpenLDAP 2.4.21 or above

### ImageMagick (premium edition)

* ImageMagick is a minefield
	* See http://legacy.imagemagick.org/script/changelog.php
	* 6.5.4 causes rotate + crop PNG unit tests to fail, due to blurry PNG output
	      and different (wrong?) PNG metadata (vs OK in 6.8.4)
	* 6.5.4-7 (RHEL 6.5) also crashes occasionally in AcquireAlignedMemory,
	      and in RelinquishMagickMemory after an UnsharpMaskImageChannel.
	* Avoid 6.7.1-\* due to colorspace bugs
	* 6.7.5 Fixes swapped RGB/sRGB colorspaces, uses sRGB by default
	* Avoid 6.7.5-5 to 6.8.0-3 as the colour management handling was changing (badly)
	* 6.8.2-4 fixes a bug that causes blurred CMYK JPEGs
	* 6.8.4-10 seems OK
	* 6.8.6-0 fixes crash sharpening cmyk images BUT...
	* Avoid 6.8.5-10 to 6.8.6-3 due to gamma bugs
	* 6.8.6-6 fixes ICC profile terminator in JPEGs
	* 6.8.6-10 - 6.8.7-1 seems OK
	* Avoid 6.8.7-4 to 6.8.7-9 with optional OpenCL enabled due to bugs
	* 6.8.8-0 has stable OpenCL acceleration for resize, sharpen, blur
	* 6.9.0-2 fixes "numerous buffer overflows" and a TIFF crash
	* 6.9.0-5 fixes defaults for RAW file decoding when missing delegates.xml
	* 6.9.1-4 fixes layer masks when flattening XCF/PSD files
	* 6.9.3-9 - 6.9.4-0 fixes several security vulnerabilities and closes
	      some possibly exploitable loopholes
	* 6.9.5-3 - 6.9.5-8 fixes further buffer overflows
	* 6.9.7-1 - 6.9.8-0 seems OK

### PDF conversion (premium edition)

* Ghostscript 8.62 works but...
	* 9.04 or above for downscaling support (much higher quality results), but...
	* 9.05 or above to fix indexed color space bugs that cause corrupt pages, so...
	* 9.06 or above is recommended

### Python

* Python 3.4 or above

### Python libraries

See `doc/requirements.txt` for the Python library versions currently required.

* Flask dependency Jinja2 - requires v2.7 or above
	* v2.6.x has a bug with filesizefilter

* Flask dependency Werkzeug - require v0.9 or above
	* We require the v0.9 changes to `ProxyFix`
