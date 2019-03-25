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

[Try it now on your own server, on Docker, or on Amazon Web Services](doc/running.md)

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

## Installation and running

See the [installation and running guide](doc/running.md) for how to run QIS on your
own server, on Docker, or on Amazon Web Services.

## Development

If you are a developer wanting to make code changes to the application, see the
[development guide](doc/development.md) for how to set up the project and run
the application in development mode.

## Important recent changes

QIS v3 is a port of QIS v2.7 to run on Python 3 only. It contains a few tidy-ups,
slightly better performance thanks to improvements in Python 3, but otherwise adds
no major new features.

QIS v4 is the first release to be fully open source. It adds an image processing
module built on the [Pillow](https://github.com/python-pillow/Pillow) library and
becomes the new QIS Standard Edition. An optional more fully featured image processing
module, built on the ImageMagick package, is [available from Quru](https://www.quruimageserver.com/)
and becomes QIS Premium Edition.

## Standard and Premium editions

The fully open source Standard Edition uses the Python-Pillow imaging library,
which is well suited to basic image resizing and cropping, and offers good
performance when colour accuracy is not critical (see the
[`IMAGE_RESIZE_GAMMA_CORRECT`](doc/tuning.md#pillow) setting) and when only
support for the most common file types is required.

The optional [upgrade to the Premium Edition](https://www.quruimageserver.com/)
swaps Pillow for a proprietary interface to the ImageMagick, Ghostscript and
LibRaw packages, bringing these advantages:

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

Topics under consideration for future versions, in no particular order:

* Image portfolios user interface
  * Addition of "add to basket" while image browsing in the admin interface
  * Addition of portfolios administration to the admin interface
  * Portfolio publishing (to zip) from the admin interface
  * Viewing a portfolio from the gallery and slideshow viewers
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
* Improve the image generation architecture for more consistent performance under load
* Replace Memcached with Redis and ditch the `qis-cache` database
* Deployment on Nginx Unit instead of Apache + mod_wsgi
