# Operating systems

QIS has been installed and is known to work on the following operating systems.

The most common problem encountered is the version of ImageMagick that ships
with the operating system. Unfortunately, ImageMagick is released continuously
and occasionally includes runs of unstable code changes.

* Ubuntu 14.04 LTS - ImageMagick 6.7.7-10 - OK
* Red Hat Enterprise Linux 6.5 - ImageMagick 6.5.4-7 - OK
* Red Hat Enterprise Linux 6.7 to 6.8 - ImageMagick 6.7.2-7 - OK
* Red Hat Enterprise Linux 7.3 - ImageMagick 6.7.8-9 - buggy colour management - see below
 
### Red Hat Enterprise Linux 7.3

ImageMagick 6.7.8-9 handles colorspace conversions and colour profiles incorrectly.
To fix this you need to install a more recent version of ImageMagick.

Remove the standard version, if it is already installed:

	$ sudo yum remove ImageMagick

Download a more recent stable version from https://www.imagemagick.org/download/linux/CentOS/x86_64/ :

	$ wget https://www.imagemagick.org/download/linux/CentOS/x86_64/ImageMagick-6.9.8-0.x86_64.rpm
	$ wget https://www.imagemagick.org/download/linux/CentOS/x86_64/ImageMagick-libs-6.9.8-0.x86_64.rpm
	(optional for development)
	$ wget https://www.imagemagick.org/download/linux/CentOS/x86_64/ImageMagick-devel-6.9.8-0.x86_64.rpm

Install the newer version:

	$ sudo yum install ImageMagick-libs-6.9.8-0.x86_64.rpm
	$ sudo yum install ImageMagick-6.9.8-0.x86_64.rpm

This fixes the colour management, but if you want to work with `SVG` files there
is a new problem. The standard `rpm` supplied by ImageMagick has a built-in SVG
renderer that does not work well. To fix this you will need to install the
`librsvg2` package and compile ImageMagick from source, specifying `--with-rsvg`
at the `configure` stage. See http://legacy.imagemagick.org/script/install-source.php
