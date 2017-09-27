# Slideshow / carousel API guide

The slideshow viewer (commonly known as a carousel) displays a number of images in rotation,
with an animated transition between them. Each image can have an associated URL to launch when
clicked. This is a popular viewer for web site home pages and for showcasing a select portfolio
of images.

## Prerequisites

The slideshow requires the [MooTools](http://mootools.net/) library, a once-popular
alternative to the now-ubiquitous [jQuery](http://jquery.com/). You can include MooTools
in your web page with the HTML:

	<script src="http://images.example.com/static/js/lib/mootools.min.js" type="text/javascript"></script>

If you want to supply your own MooTools library, the viewer requires MooTools Core and
MooTools More with the Assets, Element.Measure, Fx.Elements, and Request.JSONP components.

## Implementation

To use the slideshow API, you only need the slideshow JavaScript file in your web page:

	<script src="http://images.example.com/static/js/slideshow_view.min.js" type="text/javascript"></script>

### Adding a slideshow to a web page

You will first require an empty element to contain the slideshow. This container element must
have a known width and height so that the slideshow can determine what size to draw itself at.

For example:

	<div id="slideshow1" style="width:100%; height:400px;"></div>

Then, to load a slideshow into the container, issue the following JavaScript:

	<script>
		slideshow_view_init('slideshow1', {
			mode: 'slide',
			server: 'http://images.example.com/',
			folder: '/path/to/folder'
		});
	</script>

Where:

* The first parameter is either the ID of your container element, or the container element itself
  as a JavaScript DOM object
* The second parameter is an object that contains configuration options for the slideshow.
  This example instructs the slideshow to display all images in the `/path/to/folder` folder.

### Slideshow options

You must provide an object that maps option names to values, to specify the contents of the
slideshow and optionally control its appearance.

The mandatory options are:

* `mode` - One value from: `'slide'`, `'stack'`, or `'fade'`
* `server` - The base URL of your image server
* Either `images` - An array of image objects to display in the slideshow
* And/or `folder` - The path of a folder whose images should be displayed in the slideshow

There are also a number of optional values that you can specify if you wish to override the
default slideshow appearance:

* `controls` - Whether to show left/right arrow navigation controls, defaults to `true`
* `dots` - Whether to show clickable dot navigation controls, defaults to `true`
* `params` - An object containing image parameters to apply to every image
* `delay` - The number of seconds to show each slide for, default to `5`
* `pauseOnHover` - Whether to pause the slideshow when the mouse cursor is hovered over it,
  defaults to `true`
* `bgColor` - In `'stack'` mode, an optional image background colour

When providing an array of image objects to display, the following properties are supported for
each entry:

* `src` - Required - The path and filename of the image
* `server` - Optional - An override for the main `server` value (this is not usually required)
* `url` - Optional - A URL to follow when the image is clicked
* `[other]` - Optional - Any other properties are added to the `src` as additional image
  parameters. E.g. `tmp`, `angle`, `flip`, `top`, `left`, etc

Example slideshow options:

	<script>
		/* Shows all images in a folder */
		slideshow_view_init('slideshow1', {
			mode: 'slide',
			server: 'http://images.example.com/',
			folder: '/path/to/folder'
			params: { tmp: 'slideshow', angle: 45 }
		});
	
		/* Shows a manual list of images */
		slideshow_view_init('slideshow2', {
			mode: 'fade',
			delay: 7.5,
			server: 'http://images.example.com/',
			images: [
				{ src: 'myimages/image1.jpg' },
				{ src: 'myimages/image2.jpg', url: 'https://quru.com/' },
				{ src: 'myimages/image3.jpg', url: 'https://www.python.org/', left: 0.2, right: 0.8 }
			]
		});
	</script>

### Controlling the slideshow from JavaScript

The API provides a number of other functions for controlling the slideshow from your own code.
You can use these for example to hide the built-in navigation controls and provide your own.

* `slideshow_view_stop(container)` - stops a slideshow, or switches it to manual navigation
* `slideshow_view_start(container)` - re-starts a stopped slideshow (note slideshows start automatically
  when created)
* `slideshow_view_prev(container)` - moves a slideshow one image to the left
* `slideshow_view_next(container)` - moves a slideshow one image to the right
* `slideshow_view_index(container, index)` - moves a slideshow to an exact image index (with index
  `0` being the first)

## Demo

View this page from within QIS to see a demo.
