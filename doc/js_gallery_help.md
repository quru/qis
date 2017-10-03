# Gallery viewer API guide

The gallery viewer builds on the HTML5 canvas viewer by adding a navigable strip of thumbnail
images that can be used to browse a folder or a set of related images. Clicking on a thumbnail
then loads it as a zoomable image in the main viewer. Like the canvas viewer, the gallery can
be embedded in a web page and also supports a pop-up full-screen mode.

## Prerequisites

The gallery has the same prerequisites as the HTML5 canvas viewer,
refer to that documentation for more details.

## Implementation

To use the gallery API, you need the gallery and the HTML5 canvas viewer's CSS
and JavaScript files in your web page:

	<link href="http://images.example.com/static/styles/canvas_view.css" rel="stylesheet" type="text/css">
	<link href="http://images.example.com/static/styles/gallery_view.css" rel="stylesheet" type="text/css">
	
	<script src="http://images.example.com/static/js/canvas_view.min.js" type="text/javascript"></script>
	<script src="http://images.example.com/static/js/gallery_view.min.js" type="text/javascript"></script>

CSS files should be included before the JavaScript, so that all CSS rules have been applied
before the JavaScript starts to measure elements on the web page.

### Adding an embedded gallery to a web page

You will first require an empty element to contain the gallery. This container element must
have a known width and height so that the gallery library can determine what size to draw itself
at.

For example:

	<div id="gallery1" style="width:100%; height:400px;"></div>

Then, to load the gallery into the container, issue the following JavaScript:

	<script>
		gallery_view_init('gallery1', {
			server: 'http://images.example.com/',
			folder: '/path/to/folder'
		});
	</script>

Where:

* The first parameter is either the ID of your container element, or the container element itself
  as a JavaScript DOM object
* The second parameter is an object that contains configuration options for the gallery.
  This example instructs the gallery to display all images in the `/path/to/folder` folder.

There are in fact 3 possible parameters:

* `gallery_view_init(container, options, events)`

The `container` and `options` parameters are always required, while the `events` parameter is
optional. These are described in more detail below.

### Gallery options

You must provide an object that maps option names to values, to specify the contents of the
gallery and optionally control its appearance.

The mandatory options are:

* `server` - The base URL of your image server
* Either `images` - An array of image objects to display in the gallery
* And/or `folder` - The path of a folder whose images should be displayed in the gallery

There are also a number of optional values that you can specify if you wish to override the
default gallery behaviour:

* `thumbsize` - An object containing width and height attributes that sets the
  thumbnail image size, defaults to `{ width: 150, height: 150 }`
* `startImage` - The path and filename of the gallery image to select first
* `params` - An object containing image parameters to apply to every image
* `viewer` - An object containing options for the main image viewer. See the documentation
  for the HTML5 canvas viewer for the available viewer options.

When providing an array of image objects to display, the following properties are supported for
each entry:

* `src` - Required - The path and filename of the image
* `server` - Optional - An override for the main `server` value (this is not usually required)
* `title` - Optional - Overrides the image's default title in the main image viewer
* `description` - Optional - Overrides the image's default description in the main image viewer
* `[other]` - Optional - Any other properties are added to the `src` as additional image
  parameters. E.g. `tmp`, `angle`, `flip`, `top`, `left`, etc

Example gallery options:

	<script>
		/* Shows all images in a folder */
		gallery_view_init('gallery1', {
			server: 'http://images.example.com/',
			folder: '/path/to/folder',
			startImage: '/path/to/folder/image2.jpg',
			params: { tmp: 'gallery', quality: 80 },
			viewer: { showcontrols: 'no' }			
		});
	
		/* Shows a manual list of images */
		gallery_view_init('gallery2', {
			server: 'http://images.example.com/',
			thumbsize: { width: 120, height: 120 },
			images: [
				{ src: 'myimages/image1.jpg', tmp: 'gallery' },
				{ src: 'myimages/image2.jpg', tmp: 'gallery', left: 0.2, right: 0.8 }
				{ src: 'myimages/image3.jpg', tmp: 'gallery', title: 'The Empire State building, 1979' },
			]
		});
	</script>

### Receiving gallery events

By passing an object that maps event names to callback functions, you can be notified of actions
that occur inside the gallery and the gallery's main viewer. The available events are the same
as those documented for the HTML5 canvas viewer, plus one additional gallery event:

* `onchange` - fires when the a new image is selected in the gallery
	* Callback - `function(image_url) {}`

An example that listens for 2 events:

	<script>
		gallery_view_init('gallery1', {
			server: 'http://images.example.com/',
			folder: '/path/to/folder'
		}, {
			onchange: function(image_url) {
				alert('You selected image ' + image_url);
			},
			ondownload: function(image_url) {
				alert('You downloaded image ' + image_url);
			}
		});
	</script>

### Controlling the gallery from JavaScript

Only one function exists at present:

* `gallery_view_resize(container)` - notifies the gallery that its container has been resized,
  so that it re-calculates its size and position to correctly fill the container element

### Adding a pop-up gallery to existing image elements

You can also modify normal image elements (or elements that have a CSS `background-image`)
so that when clicked they launch a gallery in full-screen mode. The images must have
been served by QIS, that is you cannot launch a gallery of images hosted elsewhere.

Given the example HTML:

	<img id="image1" class="auto-gallery" src="http://images.example.com/image?src=/path/to/image1.jpg&tmp=thumbnail">
	<img id="image2" class="auto-gallery" src="http://images.example.com/image?src=/path/to/image2.jpg&tmp=thumbnail">
	<img id="image3" class="auto-gallery" src="http://images.example.com/image?src=/path/to/image3.jpg&tmp=thumbnail">

You can launch a standard gallery from the first image with the following JavaScript:

	<script>
		gallery_view_init_fullscreen('image1', options, events);
	</script>

Where the `options` and `events` parameters are the same as those described above.

Alternatively you can launch an automatically-generated gallery of related images
(identified by having the same class name) with the following JavaScript:

	<script>
		gallery_view_init_all_fullscreen('auto-gallery', options, events);
	</script>

Here, the server name and images to display are determined automatically from the matched images,
so that the `options` parameter is now optional. If you do provide options, all images with
the given class name are appended to your `options` object:

	<script>
		/* Click on any image with a class of 'auto-gallery' to launch a gallery
		   of all of them, with the control panel being hidden on the main viewer */
		gallery_view_init_all_fullscreen('auto-gallery', {
			viewer: {
				showcontrols: 'no'
			}
		});
	</script>

## Demo

View this page from within QIS to see a demo.
