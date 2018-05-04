# Application overview

The Quru Image Server (or "QIS" for short) is a dynamic image server, offering
a fully colour managed, dynamic resizing, templated solution that will fit the
needs of e-commerce websites, image libraries, publishers and many other businesses.

The image server hosts an image file repository, along with its own image processing
engine, management database, and dedicated web server. It can be used on its own,
or alongside a separate web site, to store, manipulate and display images on the web
in a variety of ways. Software developers can also use the built-in API to use the
image server as a back-end for creating automated imaging workflows.

## Image processing

QIS uses the popular ImageMagick package for its core image processing engine,
along with enhancements for the handling of RAW image files and PDF documents.
Imaging operations can be combined together, saved as templates, and include:

* Resizing
* Rotation
* Cropping
* Vertical and horizontal flip
* Overlays / watermarking
* Sharpen and blur
* Image format conversion (e.g. PNG to JPG)
* Image colorspace conversion (RGB, CMYK, and GRAY)
* ICC / ICM colour profile conversion and removal (for print publishing)
* Stripping of image metadata (e.g. EXIF profiles) to reduce file sizes
* PDF conversion to and from images

These operations never change the original image file, instead the resulting
image is cached in memory for future reuse. For examples of how one image can
be presented in many different ways, see the [imaging guide](image_help.md).

The supported file types vary depending on the installed version of ImageMagick,
but the following file formats are enabled by default:

* General image formats:
  * bmp, dcm, gif, jpg, png, ppm, psd, svg, tga, tif, xcf
* RAW image formats:
  * arw, cr2, mrw, nef, nrw, orf, rw2, raw, raf, x3f
* PDF / Postscript formats:
  * eps, epsi, epsf, pdf, ps

QIS has an image publishing tool that allows you to experiment with different
imaging operations, showing a preview of the resulting image.

## Embeddable image viewers

Processed (or unprocessed!) images can be displayed or made available for download
on your web site in a number of ways. The simplest and easiest is to use QIS with
the standard `<img>` or `<picture>` HTML tags. See the [imaging guide](image_help.md)
for examples.

QIS makes it easy to deliver _responsive images_ to a wide range of different devices,
whereby large devices download a large and detailed image, while small devices download
only a small, and perhaps cropped version. This is a crucial technique for making
fast loading and low bandwidth mobile web sites. Again you can see the
[imaging guide](image_help.md#responsive) for an example.

For a more interactive experience, QIS makes available a number of JavaScript
libraries that can be used for image zooming, full-screen viewing, and showcasing
multiple images. Currently the bundled viewing libraries are:

* An inline image viewer with animated zoom
  * When zooming in, only the visible portion of the enlarged image is downloaded
  * When zoomed in, the image can be panned using a mouse or touchscreen
  * Optional image information pop-up
  * Optional full-screen mode
* A function to launch a full-screen zoomable viewer when an image or a page
  element is clicked
* An inline gallery viewer, showcasing multiple images or a folder of images
* A function to launch a full-screen gallery when an image or a page element
  is clicked (e.g. to launch a gallery of all the images of a product)
* An image carousel / slideshow, showcasing multiple images or a folder of images
  * Selectable slide animation or cross-fade animation
* A lazy-loading image library
  * Images in the web page are not downloaded until they become visible, due to
    page scrolling or some other trigger

All these libraries are dependency free (vanilla JavaScript), have a responsive
layout and are touchscreen compatible. Each library has a demo page (go to the _Help_
menu), and the image publishing tool can generate sample HTML code for each library,
which you can then customise.

For the adventurous, the image server's flexible APIs make it possible build your
own image viewers!

## Image repository management

TODO - write me please

Browse, view thumbnails, image publishing tool, file management, charts
Drag & drop uploads
Portfolios (api only right now)
Server monitoring (charts)
Look for the _Folder actions_ menu
Look for the _Image actions_ menu

Management features in the web interface include:

    File system and image browser
        Add, rename, move, and delete image files and folders
    User and group administration
    Access control / user permissions administration
    System reports
        Most popular images (by number of requests, bandwidth, processing time)
        Server performance charts

## Access control

TODO - write me please

Users and groups, folders. ldap or Active Directory. 

## Developer API

TODO - write me please

Templates
Image generation
Image repository management
System administration
Link to guide

## Design and philosophy

TODO - write me please!

### Single source

One file many use, no duplication, simpler and less wasted space

### Image archive

Standard file system, copy in, copy out, standard backup tools, no lock-in

### Caching

Intended for re-use after generation
LRU eviction
