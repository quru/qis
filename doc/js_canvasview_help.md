# HTML5 canvas viewer API guide

The canvas viewer API provides a JavaScript + HTML5 animated zooming image viewer.
It also includes an integrated control panel that allows the user to download the image,
zoom in and out, read its title and description, and launch a full-screen viewing mode
(all control panel items being optional).

### Canvas element support

The HTML5 canvas element is supported in all modern web browsers, and in Microsoft Internet
Explorer from version 9 onwards.

## Implementation

To use the canvas viewer API, first add the viewer's CSS and JavaScript files to your web page:

	<link href="http://images.example.com/static/styles/canvas_view.css" rel="stylesheet" type="text/css">
	
	<script src="http://images.example.com/static/js/canvas_view.min.js" type="text/javascript"></script>

CSS files should be included before the JavaScript, so that all CSS rules have been applied
before the JavaScript starts to measure elements on the web page.

### Adding a zoomable image to a web page

You will first require an empty element to contain the image. This container element should
have a class of `imageviewer` so that the canvas viewer's CSS styles are applied to it.
The element should also have a specified width and height so that:

* The web browser knows where to reserve space for your images, and
* So that the canvas viewer library can determine what size of image to load

For example:

	<div id="viewport1" class="imageviewer" style="width:250px; height:200px;"></div>

Then, to load a zoomable image into the container, issue the following JavaScript:

	<script>
		canvas_view_init('viewport1', 'http://images.example.com/image?src=/path/to/yourimage.jpg');
	</script>

Where:

* The first parameter is either the ID of your container element, or the container element itself
  as a JavaScript DOM object
* The second parameter is the URL of the image you want to display. You can omit width and height
  values from the URL (or if specified, they are ignored) as the viewer will add its own width and
  height to match the size of your container.

If you want to change the displayed image for another, you can call `canvas_view_init()` again
with a different image URL.

There are in fact 4 possible parameters:

* `canvas_view_init(container, image_url, options, events)`

The `options` and `events` parameters are both optional JavaScript objects that are described below.

### Viewer options

By passing an object that maps option names to values, you can control the appearance and
behaviour of the viewer. The available options are:

* `title` - Overrides the image title in the control panel, defaults to the image's assigned title
* `description` - Overrides the image description, defaults to the image's assigned description
* `showcontrols` - Whether the control panel is displayed. One value from: `'yes'`, `'no'`, `'auto'`.
  Defaults to `'auto'`.
* `quality` - A boolean determining whether images are smoothed or not during zooming,
  defaults to `true`
* `animation` - The type of zoom animation. One value from: `'linear'`, `'in-out-back'`,
  `'in-out-quadratic'`, `'in-out-sine'`, `'out-back'`, `'out-quadratic'`, `'out-sine'`.
  Defaults to `'out-quadratic'`.
* `maxtiles` - The maximum number of tiles to create when zooming in, or 1 to disable tiling
  (then at maximum zoom the full image will be downloaded). Must be: `1`, `4`, `16`, `64`, or `256`.
  Defaults to `256`.
* `controls` - An inner object describing which items to display on the control panel.
  One or more of the following properties may be specified as a boolean:
	* `title` defaults to `true`
	* `download` defaults to `false`
	* `help` defaults to `true`
	* `reset` defaults to `true`
	* `fullscreen` defaults to `true`
	* `zoomin` defaults to `true`
	* `zoomout` defaults to `true`
* `doubleclickreset` - A boolean specifying whether to reset the zoom on double tap/click,
   defaults to `true`

Example options:

	<script>
		canvas_view_init('viewport1', 'http://images.example.com/image?src=/path/to/image1.jpg',
			{
				showcontrols: 'yes',    /* control panel always shown */
				animation: 'linear',    /* use a flat zoom animation */
				doubleclickreset: false /* don't respond to double clicks */
			}
		);
		
		canvas_view_init('viewport2', 'http://images.example.com/image?src=/path/to/image2.jpg',
			{
				showcontrols: 'auto',   /* user can toggle the control panel */
				controls: {
					help: false,        /* hide the help button */
					reset: false        /* hide the zoom reset button */
				}
			}
		);
	</script>

### Receiving viewer events

By passing an object that maps event names to callback functions, you can be notified of actions
that occur inside the viewer. The available events and their associated callbacks are:

* `onload` - fires when the initial image is displayed
	* Callback - `function(image_url) {}`
* `oninfo` - fires when the user views the image title and description
	* Callback - `function(image_url) {}`
* `ondownload` - fires when the full image download is invoked
	* Callback - `function(image_url) {}`
* `onfullscreen` - fires when the viewer enters (mode `true`) or leaves (mode `false`) full-screen mode
	* Callback - `function(image_url, mode) {}`

An example that listens for 2 events:

	<script>
		canvas_view_init('viewport1', 'http://images.example.com/image?src=/path/to/image1.jpg',
			null, /* use default options */
			{
				onload: function(image_url) {
					alert('Image ' + image_url + ' is now loaded');
				},
				onfullscreen: function(image_url, mode) {
					var action = (mode ? 'entering' : 'leaving');
					alert('Image ' + image_url + ' is now ' + action + ' full-screen mode');
				}
			}
		);
	</script>

### Controlling the viewer from JavaScript

The API provides a number of other functions for controlling the viewer from your own code.
You can use these for responding to web page events (such as a page resize), or for example
to hide the built-in control panel and provide your own controls.

* `canvas_view_zoom_in(container)` - zooms in on the image
* `canvas_view_zoom_out(container)` - zooms out the image
* `canvas_view_toggle_help(container)` - shows or hides the viewer's help text
* `canvas_view_toggle_image_info(container)` - shows or hides the image title and description text
* `canvas_view_toggle_fullscreen(container)` - launches or cancels the full-screen view
* `canvas_view_reset(container)` - resets the zoom level
* `canvas_view_resize(container)` - notifies the image viewer that its container has been resized,
  so that it re-calculates its size and position to correctly fill the container element

### Adding a full-screen view to an existing image element

You can also modify normal image elements (or any element that has a CSS `background-image`)
so that when clicked they launch the canvas viewer in full-screen mode. The images must have
been served by QIS, that is you cannot launch a zoomable view of an image hosted elsewhere.

Given the example HTML:

	<img id="image1" class="fs-click" src="http://images.example.com/image?src=/path/to/image1.jpg&tmp=thumbnail">
	<img id="image2" class="fs-click" src="http://images.example.com/image?src=/path/to/image2.jpg&tmp=thumbnail">
	<img id="image3" class="fs-click" src="http://images.example.com/image?src=/path/to/image3.jpg&tmp=thumbnail"
	     title="this text (or alt text) will be used as the default image title in the viewer">

You can add a full-screen click handler to just the first image with the following JavaScript:

	<script>
		canvas_view_init_image('image1', options, events);
	</script>

Or you can add a full-screen click handler to all images (identified by their class name) with
the following JavaScript:

	<script>
		canvas_view_init_all_images('fs-click', options, events);
	</script>

In either case, the `options` and `events` parameters are optional, and are the same as those
described above.

## Demo

View this page from within QIS to see a demo.
