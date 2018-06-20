# Imaging user's guide

This guide is aimed at web site editors, web developers, or content creators
who wish to display and/or modify their images.

Software developers can use this guide in conjunction with the [API user's guide](api_help.md)
for creating imaging workflows.

Features labelled with the ![Premium Edition](images/icon-premium-16.png) icon are only
available in the Premium Edition, they are ignored in the Basic Edition.

## Contents

* [A simple example](#example)
* [Default settings](#defaults)
* [Image templates](#templates)
* [Image options](#options)
    * [src](#option_src)
	* [page](#option_page)
	* [format](#option_format), [quality](#option_quality)
	* [width](#option_width), [height](#option_height), [autosizefit](#option_autosizefit), [halign](#option_halign), [valign]("#option_valign)
	* [angle](#option_angle) (rotation)
	* [flip](#option_flip)
	* [top](#option_top), [left](#option_left), [bottom](#option_bottom), [right](#option_right), [autocropfit](#option_autocropfit)
	* [fill](#option_fill)
	* [sharpen](#option_sharpen)
	* [strip](#option_strip)
	* [dpi](#option_dpi)
	* [overlay](#option_overlay), [ovsize](#option_ovsize), [ovpos](#option_ovpos), [ovopacity](#option_ovopacity)
	* [icc](#option_icc) (colour profile), [intent](#option_intent), [bpc](#option_bpc) (black point compensation)
	* [colorspace](#option_colorspace)
	* [tile](#option_tile)
	* [attach](#option_attach)
	* [xref](#option_xref)
	* [stats](#option_stats)
	* [expires](#option_expires)
	* [tmp](#option_tmp) (template)
* [Usage notes](#notes)
* [Accessing the original image](#original)
* [Delivering responsive images](#responsive)

<a name="example"></a>
## A simple example

This example assumes you have already uploaded an image named `cathedral.jpg` into the folder `buildings`.

You can now access this image at the location:  
[`http://images.example.com/image?src=buildings/cathedral.jpg`](http://images.example.com/image?src=buildings/cathedral.jpg)

More often, you will want to show the image in a web page.  
The following HTML code added to a web page will display a thumbnail version, 200 pixels wide:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200)

This example demonstrates the [width](#option_width) option. A resized copy of the image has been
generated for you, and the original file remains unchanged. This and many other image options can
be combined together, and are described in the rest of this guide.

Note: the HTML `<img>` tag itself can take further options, which are not described here.  
Consult an HTML tutorial or try an [internet search engine](https://www.google.com/search?q=html+img+tag)
for more information.

<a name="defaults"></a>
## Default settings
View this page from within QIS to see the current image settings for your server.

<a name="templates"></a>
## Image templates

A template is a group of image processing options, saved together under a single name.
You can use templates to avoid repeating the same set of image options, to make image
URLs simpler, or to define a standard set of image options in a central place.

All image options except for [src](#option_src), [xref](#option_xref), and [tile](#option_tile)
can be saved in a template. The templates already available to you are [listed above](#defaults),
and can be created or changed by an administrator. You can then apply a template to an
image using the [tmp](#option_tmp) option.

From QIS v2 onwards, a template is always used when an image is generated.
If no [tmp](#option_tmp) parameter is given then the system's [default template](#defaults)
is applied. This simplifies image generation and administration, and allows a
default value to be defined for any of the available image options. If you do
specify a template, then the system's default template is not used.

<a name="options"></a>
## Image options

For most of the options that follow, if an image template is specified (with the
[tmp](#option_tmp) option), the default value for the option is taken from that
template. If no template is specified, a default value is taken from the system's
default template. Finally, if neither of these sets a value, the default action
is to leave the image unchanged for that option.

<a name="option_src"></a>
### src
Specifies the image source, as a folder path and filename, of the original image to return or
manipulate. This is the only mandatory parameter. If you do not specify any other options, 
the image is returned with the server's [default image template](#defaults) applied.

<a name="option_page"></a>
### page ![Premium Edition](images/icon-premium-16.png)
Relevant only to multi-page file formats such as `tiff` and `pdf`, specifies which page number
to return. The first page number is 1, which is also the default value.

<a name="option_format"></a>
### format
Converts the image to a different file format, e.g. `jpg`, `tiff`, `png`, `bmp`, `gif`.
The formats available to you are [listed above](#defaults) and are set by your
system administrator.

By default, JPEG images are encoded as "baseline", the most common type.
In the context of a web site loading over a slow network, these images are drawn
from top to bottom as the data loads, and the complete image cannot be seen until
all the data has loaded. In this situation, some people prefer to use "progressive"
JPEGs. These quickly display a complete but blocky, low quality version of the
image, and then repeatedly refresh with more detail as more data loads.
The final image looks the same for both types of JPEG. To create a *progressive*
JPEG instead of baseline, use the special image format `pjpg` (or `pjpeg`).

The image as a very highly compressed `jpg` file:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200&quality=10**&format=jpg**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&quality=10&format=jpg)

The image as a `png` file (a lossless format):

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200&quality=10**&format=png**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&quality=10&format=png)

<a name="option_quality"></a>
### quality
Sets the `jpg` compression level or `png` encoding method.
This setting has no effect for other image formats.
Valid values are 1 to 100 for `jpg`, or 10 to 99 for `png`.

For `jpg`, 1 is lowest quality, highest compression and smallest file size;
while 100 is highest quality but largest file size. A value of 80 gives a reasonable 
balance between image quality and file size, while values above 95 are not recommended.
Note that if your original image is a `jpg`, you cannot improve its quality by specifying
a value of 100; you will only generate a very large image file at the same quality as the
original.

For `png` in Basic Edition, the first digit is the compression level (1 to 9, 9 being
highest compression), while the second digit must be provided but is ignored.

![Premium Edition](images/icon-premium-16.png) For `png` in Premium Edition, the first digit
is the compression level (1 to 9, 9 being highest compression), while the second digit
determines the PNG filter type in use. Unlike the `jpg` file format, the `png` format is
lossless, so changing this value does not affect image quality, only the resulting
file size and file creation speed. The "optimal" value varies for different images, and also
for whether you want to optimise for file size or processing speed. As a starting point, try
21 or 31 for simple images (those with large areas of one colour), and 79 or 99 for complex
images. The default value is 79. For a more in-depth description of this value, see the
[ImageMagick documentation](http://www.imagemagick.org/script/command-line-options.php#quality).

The image as a quality 5 <code>jpg</code> file, size 1.5 KB:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200&format=jpg**&quality=5**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&format=jpg&quality=5)

The image as a quality 70 <code>jpg</code> file, size 8.3 KB:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200&format=jpg**&quality=70**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&format=jpg&quality=70)

<a name="option_width"></a><a name="option_height"></a>
### width / height
Resizes the image to a new width and/or height, specified as number of pixels. The image cannot be 
enlarged beyond its original size. If you specify only one dimension (or set the other to 0), the
image will be kept in proportion and resized.

If you specify non-zero values for both width and height, the image will be kept
in proportion and resized to best fit into the requested area, with any surrounding
space filled with the current fill colour. The position of the image within the 
filled space is controlled by [halign](#option_halign) and [valign](#option_valign).

If you do not specify either a width or a height (or if both are 0), the image is returned
at its full original size for logged in users. For public (not logged in) users, the returned
size can be controlled by the image server's setting for a [public image width and height limit](#defaults).

A width of 200 and an automatic height:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg**&width=200**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200)

A height of 100 and an automatic width:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg**&height=100**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&height=100)

A width and height of 200, padded with grey (note: white is the default fill colour):

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg**&width=200&height=200**&fill=grey"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&height=200&fill=grey)

<a name="option_autosizefit"></a>
### autosizefit
Valid only when a width and height are both defined, requests that the final image size be 
automatically reduced in order to prevent any padding with the fill colour. With this option 
enabled, the requested size in not honoured in one direction, and the width	and height values
are re-interpreted as being the maximum acceptable size.
Valid values are true or false, 1 or 0.

Without autosizefit, requesting a width and height of 200 returns an image of exactly 200x200:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&fill=red**&width=200&height=200**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&fill=red&width=200&height=200)

With autosizefit, the returned image size is now 200x150, so that there is no vertical padding:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&fill=red**&width=200&height=200&autosizefit=1**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&fill=red&width=200&height=200&autosizefit=1)

Or for a portrait version of the same image, 150x200, so that there is no horizontal padding:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&angle=90&fill=red**&width=200&height=200&autosizefit=1**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&angle=90&fill=red&width=200&height=200&autosizefit=1)

<a name="option_halign"></a><a name="option_valign"></a>
### halign / valign ![Premium Edition](images/icon-premium-16.png)
Valid only when a width and height are both defined (and [autosizefit](#option_autosizefit) is false),
sets the position of the inner image within the area padded with fill colour. Positions are given as
a two-part value of: the inner image edge to align, and the alignment position.

For horizontal alignment (halign), valid edges are left (L), centre (C), and right (R).
For the position, 0 means the very left of the overall image and 1 is the very right,
with 0.5 being the centre. A value of "R1" therefore requests that the right edge of
the inner image be aligned to the very right of the final image.

For vertical alignment (valign), valid edges are top (T), centre (C), and bottom (B).
For the position, 0 means the very top of the overall image and 1 is the very bottom,
with 0.5 being the centre. A value of "T0.2" therefore requests that the top edge of
the inner image be aligned to 20% of the overall height of the final image.

If the requested alignment would result in some of the inner image being "chopped off",
e.g. "halign=L0.99", then the alignment will be automatically adjusted to prevent this
happening. See the [cropping](#option_left) function if you wish to achieve this.

If you do not specify alignment values, the inner image will be centred.

![Premium Edition](images/icon-premium-16.png) A padded image with the right edge of
the inner image aligned to the right:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&left=0.235&right=0.8&fill=auto**&width=200&height=150&halign=R1**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&left=0.235&right=0.8&fill=auto&width=200&height=150&halign=R1)

![Premium Edition](images/icon-premium-16.png) A padded image with the left edge of
the inner image aligned to the left:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&left=0.235&right=0.8&fill=auto**&width=200&height=150&halign=L0**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&left=0.235&right=0.8&fill=auto&width=200&height=150&halign=L0)

<a name="option_angle"></a>
### angle (rotation)
Rotates the image clockwise by a number of degrees, e.g. 0.1, 90, 180. You can specify a negative
number to rotate anti-clockwise. Valid values are -360 to 0 to 360 (where 0, 360, and -360 all
result in no rotation). If the angle is not 0, 90, 180, 270, or 360, the current fill colour is
used to fill the area surrounding the rotated image. If you also specify a width and/or height
for the image, this is applied after the rotation.

Rotation clockwise by 9.95&deg; (with the default white fill colour):

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200**&angle=9.95**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&angle=9.95)

Rotation anti-clockwise by 90&deg;:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=150**&angle=-90**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=150&angle=-90)

Rotation by 180&deg;:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200**&angle=180**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&angle=180)

<a name="option_flip"></a>
### flip
Flips the image, as if viewed in a mirror, either vertically or horizontally.
Valid values are v or h.

Vertical flip. Note this is not the same as rotating by 180 degrees:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200**&flip=v**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&flip=v)

<a name="option_top"></a><a name="option_left"></a><a name="option_bottom"></a><a name="option_right"></a>
### top / left / bottom / right
Crops the image so that only a portion of it remains. The desired crop is given 
as two points of a rectange - the left/top position (where 0, 0 is the very left/top of
the image) and the right/bottom position (where 1, 1 is the very right/bottom of the image).
Valid values are 0.0 to 1.0, and the left/top values must not overlap the right/bottom 
values. All values are optional, so that e.g. specifying top=0.5 by itself would return the 
entire bottom half of the image.

The base image without any cropping:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200)

A custom crop that removes the left and right edges. Note that the height has been constrained
in this example, since the new shape of the image would be very tall at the same width:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&height=150**&left=0.235&right=0.8**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&height=150&left=0.235&right=0.8)

The top right quarter of the image:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200**&left=0.5&top=0&right=1&bottom=0.5**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&left=0.5&top=0&right=1&bottom=0.5)

<a name="option_autocropfit"></a>
### autocropfit
Valid only when the image is being cropped, and a width and height are both defined, requests 
that the crop area be automatically expanded in order to reduce (or prevent) any padding with 
the fill colour. With this option enabled, the requested crop is not honoured in one direction,
and padding may still occur if the crop cannot be expanded far enough to meet the target width
and height. Valid values are true or false, 1 or 0.

Without autocropfit, this cropped image does not fit exactly into a 200x200 area:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200&height=200&fill=red&left=0.32&top=0.15&right=0.72&bottom=0.9"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&height=200&fill=red&left=0.32&top=0.15&right=0.72&bottom=0.9)

With autocropfit, the cropping area has now been expanded horizontally so that the resulting image fits the area:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200&height=200&fill=red&left=0.32&top=0.15&right=0.72&bottom=0.9**&autocropfit=1**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&height=200&fill=red&left=0.32&top=0.15&right=0.72&bottom=0.9&autocropfit=1)

<a name="option_fill"></a>
### fill
When a width and height are both defined (and [autosizefit](#option_autosizefit) is false), 
or if non-90 degree rotation is being applied, the requested image size is always respected even if 
the adjusted image does not fit that area. Under this scenario, the adjusted image is scaled to best 
fit the requested size, and the surrounding space is filled with the fill colour. Valid values are 
any in hexadecimal or decimal RGB "web" format, or one of a set of pre-defined English colour names. 
Examples: red, ff0000, rgb(255,0,0). If you do not specify a fill colour, white is used.

For image formats that support transparency, such as `png` and `gif`, you may use the value:
none or transparent.

![Premium Edition](images/icon-premium-16.png) In Premium Edition you may also use the special
value: auto. Setting the fill to auto causes the server to analyse the image and make a guess
at a suitable fill colour. This is most effective for images that have a consistent colour
around the edges.

The image resized as a square, using a dark grey fill colour:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg**&width=200&height=200&fill=333333**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&height=200&fill=333333)

![Premium Edition](images/icon-premium-16.png) The image rotated 20&deg;, using an automatic fill colour:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200**&angle=20&fill=auto**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&angle=20&fill=auto)

<a name="option_sharpen"></a>
### sharpen ![Premium Edition](images/icon-premium-16.png)
Applies a routine to either sharpen or blur the image. Valid values are -500 (heavy blur) to 0 (no effect) to 
500 (heavy sharpening). A small amount of sharpening (e.g. 50) sometimes enhances a resized or rotated image.

![Premium Edition](images/icon-premium-16.png) A resized portion of the sample image without sharpening:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200&bottom=0.6&left=0.27&right=0.77"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&bottom=0.6&left=0.27&right=0.77)

![Premium Edition](images/icon-premium-16.png) With a small amount of sharpening applied,
the edges in the image appear more distinct, but the image appears brighter and some detail
has been lost:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200&bottom=0.6&left=0.27&right=0.77**&sharpen=50**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&bottom=0.6&left=0.27&right=0.77&sharpen=50)

![Premium Edition](images/icon-premium-16.png) Maximum sharpening produces an interesting special effect:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200&bottom=0.6&left=0.27&right=0.77**&sharpen=500**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&bottom=0.6&left=0.27&right=0.77&sharpen=500)

![Premium Edition](images/icon-premium-16.png) The image with blur applied produces an out-of-focus effect:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&format=jpg&width=200&bottom=0.6&left=0.27&right=0.77**&sharpen=-200**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&width=200&bottom=0.6&left=0.27&right=0.77&sharpen=-200)

<a name="option_strip"></a>
### strip
Many images taken with a digital camera contain embedded information such as the photographer's name,
copyright notice, camera make and model, capture settings and so on. Some images also contain a colour
profile that describes how best to display the picture on a particular computer monitor, or how to
adjust the colours for printing on a particular printer or type of paper.
For some audiences this information can be useful, but at other times, such as 
when displaying thumbnail images on a web site, it may not be required. By enabling the strip
option, all this embedded information can be removed, resulting in a smaller file size.
Valid values are true or false, 1 or 0.

For advanced users, the strip option should be left at false (or 0) if you are dealing with CMYK images,
or with images that have an important embedded [colour profile](#option_icc). Stripping a typical RGB
image usually causes little visual change, but removing the colour profile from a CMYK image may cause
it to be displayed or printed incorrectly.

This image is 15.3 KB in size, and includes an EXIF data block with several items, including:

	Make: Nokia             Model: 3720c
	Exposure Mode: Auto     White Balance: Auto
	Colour profile: sRGB    Zoom ratio: 1

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200&quality=75**&strip=0**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&quality=75&strip=0)

This image, very nearly identical, is only 8.5 KB in size since it contains no embedded information:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200&quality=75**&strip=1**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&quality=75&strip=1)

<a name="option_dpi"></a>
### dpi
Sets the DPI (dots per inch) resolution for the image, which is often required when the image
is to be printed or included in a printable document. A value of 72 or 96 is the typical resolution
of a traditional computer monitor, while 150, 300, 600 and higher are common resolutions supported
by inkjet and laser printers. Specifying a value of 0 leaves the image's existing resolution unchanged.

The DPI value affects the physical size of an image when printed. For example, an image with a 
width of 1000 pixels (dots), at a resolution of 300 DPI, will be 1000 &div; 300 = 3 &frac13; inches, or
about 8.5cm in width, when printed. Halving the DPI to 150 would cause the same image to be twice as wide
when printed, but the result might appear "blocky" since the printed size of one pixel (dot) is then larger.

If you are converting a `pdf` file to an image, this setting controls the resulting image size.
Because this scenario converts a printable document back into a pixel-based format, the above example can be
read in reverse. That is, a section of `pdf` that measures 3 &frac13; inches, when converted at 300 DPI,
will result in an image length of 1000 pixels (dots). For `pdf` file conversions therefore, the higher
the DPI value, the larger the resulting image.

<a name="option_overlay"></a>
### overlay ![Premium Edition](images/icon-premium-16.png)
Provides the path of a second image to overlay on top of the first. This must be a local image server path, 
in the same format as [src](#option_src). By default the overlay image is centred and sized to fit
the width or height of the main image. To change this, see [ovsize](#option_ovsize), 
[ovpos](#option_ovpos), and [ovopacity](#option_ovopacity).

You can use overlays for branding or watermarking your images.
Consider using a [template](#option_tmp) to group together your standard overlay rules.
You could also apply a watermark by default in the system's default template, then use
other templates to selectively remove or alter the watermark.

Currently it is possible to remove (or rather, not apply) the watermark by providing a blank
overlay path, or by removing the template parameter from the image URL. If this is a concern, you
could pre-generate your watermarked images and save them in a new folder, and serve those
images instead.

![Premium Edition](images/icon-premium-16.png) Adding a logo to an image:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200**&overlay=logos/quru.png**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&overlay=logos/quru.png)

<a name="option_ovsize"></a>
### ovsize ![Premium Edition](images/icon-premium-16.png)
Valid only when an overlay is being applied, specifies the size of the
overlay image relative to the main image. Valid values are from 0.0 to 1.0,
where 1.0 means "use the full width or height of the main image", 0.5 means
"use half the width or height", and so on. If you do not specify a value,
1.0 is used.

The overlay image can be shrunk to any size, but will not be enlarged as
this would cause it to become blurred or blocky in appearance. For a size of
1.0 you therefore need to ensure that your overlay image has dimensions
that match or exceed your largest main image.

![Premium Edition](images/icon-premium-16.png) Setting the logo width to &frac14;
of the main image width:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200**&overlay=logos/quru.png&ovsize=0.25**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&overlay=logos/quru.png&ovsize=0.25)

<a name="option_ovpos"></a>
### ovpos ![Premium Edition](images/icon-premium-16.png)
Valid only when an overlay is being applied, specifies the position of
the overlay image inside the main image. Valid values are one of the compass points:
N, S, E, W, NE, SE, SW, NW; or C to centre. If you do not specify a value,
the overlay is centred.

If you wish to align the overlay but also have a border around it,
this can be achieved by providing a transparent border inside the
overlay image itself. This is demonstrated in the example below.

![Premium Edition](images/icon-premium-16.png) A logo containing an integral border,
aligned to the North West:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200**&overlay=logos/quru-padded.png&ovsize=0.4&ovpos=NW**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&overlay=logos/quru-padded.png&ovsize=0.4&ovpos=NW)

<a name="option_ovopacity"></a>
### ovopacity ![Premium Edition](images/icon-premium-16.png)
Valid only when an overlay is being applied, defines the opacity level of the overlay,
and to what degree it blends into the main image. Valid values are from 0.0 to 1.0,
where 0.0 is fully transparent and 1.0 is fully opaque. If you do not specify a value,
1.0 is used.

![Premium Edition](images/icon-premium-16.png) Setting the logo to be semi-transparent,
useful as a watermark effect:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200**&overlay=logos/quru.png&ovopacity=0.3**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&overlay=logos/quru.png&ovopacity=0.3)

<a name="option_icc"></a><a name="option_intent"></a>
### icc (colour profile) / intent ![Premium Edition](images/icon-premium-16.png)
These options are intended only for advanced users.

Attaches and applies an International Color Consortium (ICC) colour profile to the
image, possibly changing the image's [colour model / colorspace](#option_colorspace),
to alter the way the colours appear on screen or on paper. Most commonly this option
is used in print publishing, when the image is intended to be printed on a specific
brand of paper. The ICC profiles available to you are [listed above](#defaults) and
are set by your system administrator.

You should also specify a rendering intent when applying an ICC profile, where valid
values are: saturation, perceptual, absolute, or relative. The rendering intent alters
the way in which  the ICC profile is applied (further detail is beyond the scope of
this guide).

RGB profiles are used to target on-screen applications, such as the web.  
CMYK profiles are used to target printer and paper variations in publishing.
Some web browsers fail to display CMYK images correctly, or even at all.

If you want to apply a CMYK profile but then convert the image back to RGB (for example
to preview the effect on-screen), you can add the [colorspace](#option_colorspace)
directive.

If you want to remove the colour profile from the image after applying it, enable
the [strip](#option_strip) option. This is often appropriate for RGB images, but not
in general for CMYK images.

![Premium Edition](images/icon-premium-16.png) The sample image, with a
greyscale conversion applied with 'perceptual' intent:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200**&icc=greyscale&intent=perceptual**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&icc=greyscale&intent=perceptual)

<a name="option_bpc"></a>
### bpc (black point compensation) ![Premium Edition](images/icon-premium-16.png)
This option is intended only for advanced users.

Valid only when applying an ICC colour profile with the 'relative' rendering intent, 
determines whether Black Point Compensation is applied during the process.
Valid values are true or false, 1 or 0.

![Premium Edition](images/icon-premium-16.png) A print-based colour profile applied
with 'relative' intent and without black point compensation:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200**&icc=UncoatedFOGRA29&intent=relative&bpc=0**&colorspace=rgb"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&icc=UncoatedFOGRA29&intent=relative&bpc=0&colorspace=rgb)

![Premium Edition](images/icon-premium-16.png) With black point compensation,
the image has a tone that more closely matches the original:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200**&icc=UncoatedFOGRA29&intent=relative&bpc=1**&colorspace=rgb"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&icc=UncoatedFOGRA29&intent=relative&bpc=1&colorspace=rgb)

<a name="option_colorspace"></a>
### colorspace ![Premium Edition](images/icon-premium-16.png)
This option is intended only for advanced users.

Converts the internal colour model of the image to either Red-Green-Blue, Cyan-Magenta-Yellow-blacK,
or Greyscale. Most image formats have support for RGB colour, but support varies for the other types. 
For example, PNG images do not support CMYK colour.
Valid values are: RGB, CMYK, or GRAY.

RGB images are normally required for on-screen applications, such as in a web page.  
CMYK images are used for print publishing.
Some web browsers fail to display CMYK images correctly, or even at all.

This option is most useful for quickly converting existing print-ready images from CMYK to RGB
so that they can be previewed on-screen. For converting images to CMYK, this operation assumes
a default paper type that may not be appropriate, and it is better to apply a specific CMYK
[colour profile](#option_icc) instead.

If used together with [icc](#option_icc), then the ICC profile is applied first and the
`colorspace` conversion second. If [strip](#option_strip) is also enabled, this removes the
embedded colour profile last.

The unaltered RGB sample image:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200)

![Premium Edition](images/icon-premium-16.png) The sample image with a CMYK print
colour profile applied, converted back to RGB for display purposes:

<code class="imagecode">&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200&icc=USSheetfedUncoated&intent=relative**&colorspace=rgb**"></code>
![](//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&icc=USSheetfedUncoated&intent=relative&colorspace=rgb)

<a name="option_tile"></a>
### tile
The tile parameter is used internally by the image server for breaking up large images into smaller 
pieces, but it can be used anywhere to obtain a grid of component images from a single image.
The tile is specified as 2-part number: a tile number, and a grid size. The grid size must be one
value from: 4 (2x2), 9 (3x3), 16 (4x4), 25, 36, 49, 64, 81, 100, 121, 144, 169, 196, 225, and 256 (16x16).
The tile number to create can then be any value between 1 (the top left tile) and the grid size (the bottom right tile).

Tile creation is always carried out last, so that it does not affect any other options
you have in effect. This means you can rotate, resize and crop an image how you want
it, then create the tiles.

Because the grid always has the same number of tiles vertically as horizontally, the resulting
tiles will be the same shape as your original image. Only if your original image is a square
will the resulting tiles be square.

Also note that some image sizes are not divisible exactly by the number of tiles,
vertically and/or horizontally. In this case, the tile size towards the top/left will
be rounded down and kept consistent. The bottom/right-most strip of tiles will be
slightly larger to make up the difference. For example, a 100x100 image, with a grid
size of 9 (3x3), will create tiles of size 33, 33, 34 from left to right, and 
33, 33, 34 from top to bottom.

When creating tiles, consider adding the [strip](#option_strip) option, so as to
trim the final size of each image.

This example shows tiles 1 and 4, with a grid size of 4:

<code class="imagecode">
&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200**&tile=1:4**">  
&lt;img src="//images.example.com/image?src=buildings/cathedral.jpg&width=200**&tile=4:4**">
</code>
<table>
	<tr>
		<td><img src="//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&tile=1:4" /></td>
		<td></td>
	</tr>
	<tr>
		<td></td>
		<td><img src="//images.example.com/image?src=buildings/cathedral.jpg&stats=0&width=200&tile=4:4" /></td>
	</tr>
</table>

<a name="option_attach"></a>
### attach
Usually, when dealing with images on a web site, you will want your user's web browser to 
display the images. On occasion, however, you may want to offer the user a way of downloading 
the underlying image file instead of displaying it. This can be achieved by setting the image 
to be an attachment. When the image is an attachment, the web browser will prompt the user to 
save the file on their computer under its original filename.
Valid values are true or false, 1 or 0.

The following link downloads the sample image as a `png` file:  
<code>
[http://images.example.com/image?src=buildings/cathedral.jpg&format=png**&attach=1**](http://images.example.com/image?src=buildings/cathedral.jpg&format=png&attach=1)
</code>

<a name="option_xref"></a>
### xref
For some imaging applications, email marketing campaigns in particular, it can be useful to 
record who has viewed an image. The xref option allows you to add a tracking reference 
(perhaps unique) to an image, by adding <code>**&xref=your-own-reference**</code> to the 
image options. Then, whenever the image is requested from the server, the server will
make a call to a third party application, passing your tracking reference across to it.

For xref to take effect, your system administrator must have first configured the link to the 
third party application. When using xref, you should ensure that the value does not contain 
any personally identifiable information.

<a name="option_stats"></a>
### stats
By default, statistics about image request are recorded so that the built-in
management reports can show you when the service is busiest and identify the most popular images.
You can selectively disable image-level statistics by adding <code>**&stats=0**</code>
to the image options. This prevents the image's own view, download and bandwidth counts from
increasing, but does not affect the system-level statistics.

You may find this option useful to exclude certain images from the "top images" report,
for example a company logo that appears on every web page.

<a name="option_expires"></a>
### expires (client caching duration)
This option can only be set in an [image template](#option_tmp), not on individual images.

Sets the number of seconds for which a web browser should cache an image locally before
requesting it again from the server. This is only an instruction to the client; it has
no effect on the caching of images on the server.

For images that are uploaded once and do not change, this value should be set as `31536000`
(1 year), meaning the web browser should cache the image locally for as long as possible.

For images that may change occasionally, a value of `604800` (7 days) or more is recommended.

A value of `-1` means expire the image immediately, and do not cache it at all. If your
images are being used on a web site, this will greatly increase the number of requests
made to your image server, increase the data transferred, and cause your web pages to
load more slowly.

A value of `0` means do not provide any expiry time to the client. In this case the client
is free to decide its own caching strategy, and different web browsers will behave in
different ways. In reality, most web browsers will not cache the image.

If you do not specify a value, the default is 7 days.

<a name="option_tmp"></a>
### tmp (template)
Templates, as [described above](#templates), group together a standard set of image
processing options. If you find that you commonly use the same set of image options,
you should consider moving them into a template. The templates already available to
you are [listed above](#defaults) and are controlled by an administrator.

When using a template:

* The image URL is shorter and neater, as you only need to provide the template name
  instead of all the associated options.
* The common image options are defined only in one place, making future changes easier.
* All images that use the template are automatically updated when the template is changed.
* Further image options can be added alongside the template name. This allows a template
  to provide a base set of image options, which can then be selectively overridden.

Note that as of QIS v2, if you do not specify a template for an image then the system's
default template will be applied automatically. If you **do** specify a template, the
system's default template is **not** applied, your chosen template replaces it.

A 200x200 size `jpg` image with typical options for inclusion on a web site:

<code class="imagecode">&lt;img class="border" src="//images.example.com/image?src=buildings/cathedral.jpg**&format=jpg&quality=80&colorspace=rgb&width=200&height=200&strip=1**"></code>
<img class="border" src="//images.example.com/image?src=buildings/cathedral.jpg&stats=0&format=jpg&quality=80&colorspace=rgb&width=200&height=200&strip=1" />

The same image and options, defined instead using the sample template `SmallJpeg`:

<code class="imagecode">&lt;img class="border" src="//images.example.com/image?src=buildings/cathedral.jpg**&tmp=smalljpeg**"></code>
<img class="border" src="//images.example.com/image?src=buildings/cathedral.jpg&stats=0&tmp=smalljpeg" />

Options in addition to the template name are either added to or replace those in the template:

<code class="imagecode">&lt;img class="border" src="//images.example.com/image?src=buildings/cathedral.jpg**&tmp=smalljpeg&angle=90&quality=10**"></code>
<img class="border" src="//images.example.com/image?src=buildings/cathedral.jpg&stats=0&tmp=smalljpeg&angle=90&quality=10" />

<a name="notes"></a>
## Usage notes

### Order of command precedence
There are up to 3 places where image options (e.g. quality) can be specified:

1. Within the image URL
2. Within a custom image template
3. Within the default image template

Options in the URL (1) always take precedence. If an image template (2) is specified then
it provides all the remaining options. Or if no image template is specified then the
default template (3) provides all the remaining options.

The order of precedence then is (1) then (2) **or** (1) then (3).
There is no fall-back from (2) to (3).

As an example, if the server's default template has `jpg` format,
and the template 'custom' specifies `png` format:

<code>**src=myimage&tmp=custom&format=gif**</code> would return a `gif` image, from (1).  
<code>**src=myimage&tmp=custom**</code> would return a `png` image, from (2).  
<code>**src=myimage&format=gif**</code> would return a `gif` image, from (1).  
<code>**src=myimage**</code> would return a `jpg` image, from (3).

### Order of imaging operations
Some operations, when combined together, would produce a different result if they were performed
in a different order. Images are always processed in this order, regardless of the order in
which you specify the commands:

1. Flip
2. Rotate
3. Crop
4. Resize
5. Overlay ![Premium Edition](images/icon-premium-16.png)
6. Tile
7. Apply ICC profile ![Premium Edition](images/icon-premium-16.png)
8. Set colorspace ![Premium Edition](images/icon-premium-16.png)
9. Strip

Therefore, a request for <code>**src=myimage&width=200&left=0.2&right=0.8&angle=45**</code>
would first rotate the image by 45&deg; clockwise, then crop to remove the left and right edges, then
resize the result to a 200 pixel width.

<a name="original"></a>
## Accessing the original image
At the beginning of this guide, it was shown that you can access an image by providing no 
options other than its filename:  
<code>
[http://images.example.com/image?src=buildings/cathedral.jpg](http://images.example.com/image?src=buildings/cathedral.jpg)
</code>

You might think that this would return the original unaltered image, but in fact it probably
does not. The server's [default image template](#defaults) will be applied, and the resulting
image might be quite different from the original.

In order to obtain the full size original image you must instead use a different URL:  
<code>
[http://images.example.com/**original**?src=buildings/cathedral.jpg](http://images.example.com/original?src=buildings/cathedral.jpg)
</code>

This command takes the mandatory [src](#option_src) parameter. It optionally accepts the
[attach](#option_attach) parameter so you can download the file instead of displaying it,
the [xref](#option_xref) parameter for usage tracking,
and the [stats](#option_stats) parameter. All other options are ignored.

Users must have the *download* permission to use the `original` URL.
This allows you to restrict access to the full images by whether users are public or logged-in,
and/or by folder.

<a name="responsive"></a>
## Delivering responsive images
_Responsive images_ is a term used in web development for a technique whereby different
sizes of the same image are made available on a web site, for use by different devices
with different screen sizes. The idea is that large devices download a large and detailed
image, while small devices download only a small, and perhaps cropped version. This is a
crucial technique for making fast loading and low bandwidth mobile web sites.

Getting responsive images in QIS is easy using the [width](#option_width) and
[height](#option_height) image parameters.

You can either use the `<img srcset=...>` HTML tag:

	<img src="https://images.example.com/image?src=buildings/cathedral.jpg&width=800"
	  srcset="https://images.example.com/image?src=buildings/cathedral.jpg&width=480 480w,
	          https://images.example.com/image?src=buildings/cathedral.jpg&width=800 800w,
	          https://images.example.com/image?src=buildings/cathedral.jpg&width=1200 1200w"
	   sizes="100vw">

Or you can use responsive CSS with background images:

    .my-image {
        width: 480px;
		height: 360px;
        background-image: url("https://images.example.com/image?src=buildings/cathedral.jpg&width=480");
    }
    @media screen and (min-width: 481px) and (max-width: 800px) {
        .my-image {
            width: 800px;
			height: 600px;
            background-image: url("https://images.example.com/image?src=buildings/cathedral.jpg&width=800");
        }
    }
    @media screen and (min-width: 801px) {
        .my-image {
            width: 1200;
			height: 900px;
            background-image: url("https://images.example.com/image?src=buildings/cathedral.jpg&width=1200");
        }
    }
