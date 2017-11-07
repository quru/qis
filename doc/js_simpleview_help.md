# Simple viewer API guide

The simple viewer API provides a pure JavaScript method for displaying zoom-enabled
images on your web site. It is the most basic of the available image viewers and in
most cases you will want to use the HTML5 canvas viewer instead.

_Advantages_

* Easy to implement
* No cross-domain (same origin policy) issues
* Very small library size
* Low bandwidth displaying the initial image

_Disadvantages_

* Provides a very basic user experience
* Every zoom creates and downloads a new image from the server, which can be slow
* No image caching

## Implementation

To use the simple viewer API, first add the viewer's CSS and JavaScript files to your web page:

	<link href="http://images.example.com/static/styles/simple_view.css" rel="stylesheet" type="text/css">
	
	<script src="http://images.example.com/static/js/simple_view.min.js" type="text/javascript"></script>

CSS files should be included before the JavaScript, so that all CSS rules have been applied
before the JavaScript starts to measure elements on the web page.

### Adding a zoomable image to a web page

You will first require an empty element to contain the image. This container element should
have a class of `imageviewer` so that the simple viewer's CSS styles are applied to it.
The element should also have a specified width and height so that:

* The web browser knows where to reserve space for your images, and
* So that the simple viewer library can determine what size of image to load

For example:

	<div id="viewport1" class="imageviewer" style="width:250px; height:200px;"></div>

Then, to load a zoomable image into the container, issue the following JavaScript:

	<script>
		simple_view_init('viewport1', 'http://images.example.com/image?src=/path/to/yourimage.jpg');
	</script>

Where:

* The first parameter is either the ID of your container element, or the container element itself
  as a JavaScript DOM object
* The second parameter is the URL of the image you want to display. You can omit width and height
  values from the URL (or if specified, they are ignored) as the viewer will add its own width and
  height to match the size of your container.

If you want to change the displayed image for another, you can call `simple_view_init()`
again with a different image URL.

### Usage notes

* When the image is displayed, you can click to zoom in, up to 9 times
* The zoomed image is re-centered on the click position
* Hold the `shift` key and click to zoom out
* Hold the `alt` key and click to re-centre the image without zooming

To reset the zoom level, issue the following JavaScript:

	<script>
		simple_view_reset('viewport1');
	</script>

### Enabling zoom on an existing image element

If you would rather load images with the rest of your HTML instead of loading them dynamically
with JavaScript, you can provide your own `img` elements. One advantage of this is that images
will then be visible (though not zoomable) to users who do not have JavaScript support or who
have it disabled.

A container element is still required so that the simple viewer library can determine the size 
of the imaging area without having to wait for all the images to load.

	<div class="imageviewer" style="width:250px; height:200px;">
		<img id="yourimage" src="http://images.example.com/image?src=/path/to/yourimage.jpg&width=250&height=200">
	</div>

When providing your own `img` elements, you must include a width and height in the image URL,
either by specifying a template or by explicitly setting the width and height values.
If you do not do so, the image server will return the image at its full size
(see the imaging user's guide for more information).

Then, to enable zooming on the image, issue the following JavaScript:

	<script>
		simple_view_init_image('yourimage');
	</script>

Where:

* The parameter is either the ID of your image element,
  or the image element itself as a JavaScript DOM object

Usage notes are the same as above, and to reset the zoom level, issue the following JavaScript:

	<script>
		simple_view_reset_image('yourimage');
	</script>

If you want to change the displayed image for another, you will need to write your own JavaScript
to either replace the `img` element, or to change the value of its `src` attribute.
You must then call `simple_view_init_image()` again.

## Demo

View this page from within QIS to see a demo.
