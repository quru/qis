# Known good versions of application dependencies

* Python 2.6 or 2.7
	* Minimum 2.6.5 (we are affected by a deadlock bug in < 2.6.5)
	* Prefer 2.7 (the latest revision available)
* PostgreSQL 8.3 or above, prefer 9.x
* Memcached 1.2.8 or above
* libmemcached 1.0.16 (0.32 or above is required)
* Membase 1.7.1 (note: Membase support is untested since 2011)
* Apache 2.2.17 or above
* mod_wsgi 3.2.7 or above
* OpenLDAP 2.4.21
* ImageMagick is a minefield
	* See http://www.imagemagick.org/script/changelog.php
	* 6.5.4 causes rotate + crop PNG unit tests to fail, due to blurry PNG output
	      and different (wrong?) PNG metadata (vs OK in 6.8.4)
	* 6.5.4-7 (RHEL 6.5) also crashes occasionally in AcquireAlignedMemory,
	      and in RelinquishMagickMemory after an UnsharpMaskImageChannel.
	* Avoid 6.7.1-* due to colorspace bugs
	* 6.7.5 Fixes swapped RGB/sRGB colorspaces, uses sRGB by default
	* Avoid 6.7.5-5 to 6.8.0-3 as the colour management handling was changing (badly)
	* 6.8.2-4 fixes a bug that causes blurred CMYK JPEGs
	* 6.8.4-10 seems OK
	* 6.8.6-0 fixes crash sharpening cmyk images BUT...
	* Avoid 6.8.5-10 to 6.8.6-3 due to gamma bugs
	* 6.8.6-6 fixes ICC profile terminator in JPEGs
	* 6.8.6-10 - 6.8.7-1 appear to be fairly stable!
	* Avoid 6.8.7-4 to 6.8.7-9 with optional OpenCL enabled due to bugs
	* 6.8.8-0 has stable OpenCL acceleration for resize, sharpen, blur
	* 6.9.0-2 fixes "numerous buffer overflows" and a TIFF crash

# Known good versions of dependencies of the dependencies

* lcms (little CMS) 2.1
* libevent 1.4.14
* Ghostscript 8.62 but...
	* 9.04 or above for downscaling support (much higher quality results), but...
	* 9.05 or above to fix indexed color space bugs that cause corrupt pages, so...
	* 9.06 is recommended

# Python libraries

See `doc/requirements.txt` for Python library versions.

* Flask dependency Jinja2 - require v2.5.5 or 2.7 or above
	* v2.6.x has a bug with filesizefilter

* Flask dependency Werkzeug - require v0.9 or above
	* We require the v0.9 changes to `ProxyFix`
