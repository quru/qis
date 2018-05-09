# Application overview

The Quru Image Server (or "QIS" for short) is a dynamic image server, offering
a fully colour managed, dynamic resizing, templated solution that will fit the
needs of e-commerce websites, image libraries, publishers and many other businesses.

The image server hosts an image file repository, along with its own image processing
engine, management database, and dedicated web server. It can be used on its own,
or alongside a separate web site, to store, manipulate and display images on the web
in a variety of ways. A built-in web interface provides repository browsing, reports,
and system administration facilities. Software developers can also use the built-in
API to use the image server as a back-end for creating automated imaging workflows.

## Image processing

QIS uses the popular ImageMagick package for its core image processing engine,
along with enhancements for the handling of RAW image files and PDF documents.
Imaging operations can be combined together, saved as templates, and include:

* Resizing
* Rotation
* Cropping, tiling
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

* General image formats: _bmp, dcm, gif, jpg, png, ppm, psd, svg, tga, tif, xcf_
* RAW image formats: _arw, cr2, mrw, nef, nrw, orf, rw2, raw, raf, x3f_
* PDF / Postscript formats: _eps, epsi, epsf, pdf, ps_

QIS has an image publishing tool in the web interface that allows you to experiment
with different imaging operations, showing a preview of the resulting image.

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
libraries that can be used to provide image zooming, full-screen viewing, and the
showcasing of multiple images. Currently the bundled viewing libraries are:

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

All these libraries are dependency free (they are _vanilla JavaScript_),
have a responsive layout, and are touchscreen compatible. Each library has a demo
page (go to the _Help_ menu), and the image publishing tool can generate sample
HTML code for each library, which you can then customise.

For the adventurous, the image server's flexible APIs make it possible build your
own image viewers!

## Image repository management

As well as serving up images, the image server acts as a central place for storing,
browsing, and managing your entire image library. Management features available in
the web interface include:

* File system browsing
    * Compact list view or a grid view of thumbnail images
    * Add, move, rename, and delete image files and folders
      (use the _Folder Actions_ menu)
* Image details viewing, including embedded EXIF data and file change history
* Image publishing tool with dynamic image preview (use the _Image Actions_ menu)
* Image uploads via drag & drop or local file selection
* Image usage charts
    * Chart the number of views, number of downloads, bandwidth used, processing time,
      and response times for individual images
* Server performance charts
    * See the top images by most viewed, most processed, most bandwidth, and slowest
      responses
    * Chart the server's (or the cluster's) overall number of image views, downloads,
      caching success, performance, CPU and memory usage
* The creation of image collections - selected images that are viewable on a web page
  and downloadable as a single zip file (currently this is named _portfolios_ and is
  only available using the developer API)
* System administration
    * Define image processing templates
    * User and group management
    * User access control and image permissions

## Access control

The image server holds a database of users and groups (which can act like _roles_
in other systems). Users are only required for logging into the web interface or
accessing the API, so at its simplest you only need 1 user account for browsing
the repository or performing administration. User accounts can be taken from an
LDAP or Active Directory server in a corporate environment.

Groups have a list of members (users) and are used for defining access permissions
in the application. An administrator can grant various privileges to a group:

* Access to reports
* Creation of portfolios
* Files and folders administration
* User and group membership administration
* User and group full administration (including permissions)
* Super user - access to everything

Groups are also used to set the level of access that internal users and the public
have to your images. You can keep all of your images private, have all of them public,
or anything in between. This is achieved by choosing a folder from the repository,
and then a group, and setting what level of access is allowed. For each folder and
group, the available levels are:

* No access
* View only
* View and download the original image file
* Plus change image attributes
* Plus upload new images
* Plus delete images
* Plus create sub-folders
* Plus delete sub-folders (full access)

The access level you set is automatically inherited by a folder's sub-folders too.
So when you set the access for the image repository's _root_ folder, this acts as
the default permission for all other folders.

A special group called _Public_ represents anonymous users on the internet who might
request an image from your server. This is used to allow or deny public access to
your images.

When first starting out, you only need to review and perhaps change 2 folder
permissions:

* The _root_ folder and the _Public_ group - what level of access the public
  have to all your images by default
* The _root_ folder and the _Normal users_ group - what level of access a
  basic user (who is logged into the web interface or the API) has to all your
  images by default

You can then override these defaults later at the sub-folder level.
If at any point the _Public_ access level is greater than a logged-in user's
access via their groups, the more permissive public access level will be applied.

## Developer API

Everything that QIS does can be controlled programmatically through its Application
Programming Interface (API). This enables the image server to be integrated with
other systems, and for scripts to be developed to perform automated imaging workflows.

The API itself uses the common [REST](https://en.wikipedia.org/wiki/Representational_state_transfer)
style, and operates over HTTPS using standard web protocols. The functionality
provided includes:

* Authentication (login) and access control
* Image processing
* Image repository browsing and management
* Portfolio creation and management
* Image uploads
* Image template management
* System administration

For more information, technical details and examples of use, see the
[API guide](api_help.md).

## Design goals and philosophy

The image server was developed with a few goals in mind. A discussion of these
isn't entirely necessary, but it may be useful to understand why QIS does things
in certain ways and how it differs from other dynamic image servers out there.

### Single source, multiple uses

QIS operates on the basis that one image file is uploaded, and multiple uses of
that file are possible from then on. If you are serving responsive images on a
web site, one image can be served in several different sizes and with different
crops for the best appearance. If you host a PDF document on the server, you can
present users with a preview of the front cover (or indeed any other page),
without them needing a PDF viewer and without requiring a separate image file to
be stored.

There is no duplication of image files on disk, which keeps the file storage
simple, with less to go wrong and less wasted space.

### A simple image archive

The image repository is stored as normal files and folders in a normal file
system. If you have an existing folder of images on a PC or a server, you can
point QIS at that folder and the images will be immediately visible in QIS's
web interface and for publishing on the web.

The image server does not mind if files appear and disappear in the repository,
it does not mind if you use FTP or SCP or RSYNC or a network file system to
bring in files from other places and other systems.

Because it operates from a standard file system, there is no lock-in with QIS,
you own your data, and you can easily take your images elsewhere. You can also
use standard file managers and standard backup tools to manage your files and
keep them safe.

None of this can be said for image services that operate in The Cloud.

### Performance and caching

QIS makes use of an in-memory cache of generated images for achieving its
performance goals. This design relies on the assumption that once you have a 
requested a particular image (applying some specific processing parameters),
that the image generated will be needed again soon. This is usually true of
web pages, where the same images (or a fixed number of variants of them) are
repeatedly delivered to everyone that visits the web page.

The caching engine currently used is Memcached. This has some drawbacks, but it
is fast, simple, and reliable. Used alongside the image server, Memcached stores
images and data in memory up until a memory limit is reached. This limit needs
to be tuned to be as large as possible while still leaving some working memory
free for image processing and anything else running on the server. Once the limit
is reached, the next item to be stored causes the [least recently used](https://en.wikipedia.org/wiki/Cache_replacement_policies#Least_recently_used_(LRU))
thing to be evicted from the cache. In other words, Memcached prioritises keeping
hold of the most frequently used images and data.

If you generate images that are always unique, or will not be re-used in the
near future, then QIS will still work for you but it will not be very fast.

On the other hand, when you request an image that has already been generated and
is still in the cache, it typically takes less than 2 milliseconds for the server
to check your access permissions and fetch the image. To this time you need to
add the time taken to create a network connection and transfer the data back
over the network.
