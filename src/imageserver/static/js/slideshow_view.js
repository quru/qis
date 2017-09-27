/*!
	Document:      slideshow_view.js
	Date started:  05 Feb 2013
	By:            Matt Fozard
	Purpose:       Quru Image Server image slideshow library
	Requires:      common_view.js
	               MooTools Core 1.3 (no compat)
	               MooTools More 1.3 - Assets, Element.Measure, Fx.Elements, Request.JSONP
	Copyright:     Quru Ltd (www.quru.com)
	Licence:

	This program is free software: you can redistribute it and/or modify
	it under the terms of the GNU Affero General Public License as published
	by the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.

	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU Affero General Public License for more details.

	You should have received a copy of the GNU Affero General Public License
	along with this program.  If not, see http://www.gnu.org/licenses/
*/
/*	
	Notable modifications:
	Date       By    Details
	=========  ====  ============================================================
	20Feb2013  Matt  Changed image centering to work across IE7 - 9
	22Feb2013  Matt  Added background colour for stack mode
	05Jul2013  Matt  Added support for adding image parameters
	29Jul2013  Matt  Added fps option
	19Feb2015  Matt  Use 1 timer for animation instead of 2
	20Feb2015  Matt  Pause on mouse hover, pause when page invisible
	23Feb2015  Matt  Add prev, next functions, arrows and dots UI controls
    28Sep2017  Matt  Remove MooTools, remove JSONP
*/

/**** Slideshow class ****/

function ImgSlideshow(container, userOpts) {
	// Default options
	this.options = {
		controls: true,
		dots: true,
		dotColor: '#666666',
		dotSelectedColor: '#dddddd',
		mode: 'slide',
		delay: 5,
		pauseOnHover: true,
		server: '',
		folder: '',
		images: [],
		params: {},
		fps: 50,
		duration: 1000,
		bgColor: 'white',
		transition: Fx.Transitions.Quad.easeInOut
	};
	// Apply options
	if (userOpts != undefined) {
		this.options = Object.merge(this.options, userOpts);
	}
	
	// Normalise servers and folders
	this.options.server = this._add_slash(this.options.server);
	this.options.folder = this._add_slash(this.options.folder);
	this.options.images.each(function (im) {
		if (im.server) im.server = this._add_slash(im.server);
	}.bind(this));
	
	this.imageSize = {
		width: 0,
		height: 0
	};
	
	this.ctrEl = document.id(container);
	this._hover_in_fn = this._hover_in.bind(this);
	this._hover_out_fn = this._hover_out.bind(this);
	this._visibility_change_fn = this._visibility_change.bind(this);
	this.pvAPI = (document.hidden !== undefined);
	this.arrowEls = [];
	this.imageEls = [];
	this.wrapEls = [];
	this.animTimer = null;
	this.ready = false;
	this.running = false;
	this.animating = false;
	this.direction = 1;
	this.imageIdx = 0;
	this.layout();
}

// Call init first.
// Load sequence is data-ready then images-ready then create-ui then start.
ImgSlideshow.prototype.init = function() {
	this.setMessage('Loading slideshow...');
	if (this.options.folder)
		this.addFolderImages();
	else
		this.onDataReady(null);
	
	// Load arrow controls
	if (this.options.controls) {
		var arrImgs = ['arrow-left.png', 'arrow-right.png'],
		    arrEvents = [this.prev, this.next];
		for (var i = 0; i < arrImgs.length; i++) {
			this.arrowEls[i] = new Element('a', {
				href: '#',
				html: '<img src="' + this.options.server + 'static/images/slideshow/' + arrImgs[i] + '"> ', // Trailing space for IE7 hasLayout
				styles: {
					'position': 'absolute',
					'z-index': '10',
					'text-decoration': 'none',
					'border': 'none'
				},
				events: {
					'click': arrEvents[i].bind(this)
				}
			});
		}
	}
};

// Free up object handles
ImgSlideshow.prototype.destroy = function() {
	if (this.pvAPI) {
		document.removeEvent('visibilitychange', this._visibility_change_fn);
	}
	if (this.options.pauseOnHover) {
		this.ctrEl.removeEvent('mouseenter', this._hover_in_fn);
		this.ctrEl.removeEvent('mouseleave', this._hover_out_fn);
	}
	this.stop();
	this.ready = false;
	this.ctrEl.empty();
	this.imageEls.each(function (el) { el.destroy(); });
	this.wrapEls.each(function (el) { el.destroy(); });
	this.imageEls.empty();
	this.wrapEls.empty();
};

// Reads the current size/position of the container element,
// and sets some necessary styles to it
ImgSlideshow.prototype.layout = function() {
	// Get container size
	var ctrSize = this.ctrEl.getComputedSize();
	// Fallback
	if ((ctrSize.width == 0) && (ctrSize.height == 0))
		ctrSize = { width: this.ctrEl.clientWidth, height: this.ctrEl.clientHeight };
	// Set image sizes
	this.imageSize.width = ctrSize.width;
	this.imageSize.height = ctrSize.height;
	// Set required container styles
	this.ctrEl.setStyles({
		'position': 'relative',  // So that child elements can be positioned absolutely
		'overflow': 'hidden',
		'text-align': 'center',
		'line-height': ctrSize.height + 'px'
	});
};

ImgSlideshow.prototype.setMessage = function(msg) {
	this.ctrEl.innerHTML = '<span style="font-size: small">' + msg + '</span>';
};

ImgSlideshow.prototype.addFolderImages = function() {
	var dataURL = this.options.server + 'api/v1/list?path=' + encodeURIComponent(this.options.folder);
    QU.jsonRequest(
        dataURL,
        'GET',
        function(xhr, jobj) { this.onDataReady(jobj); }.bind(this),
        function(xhr, msg)  { this.setMessage('');    }.bind(this)
    ).send();
};

ImgSlideshow.prototype.onDataReady = function(jsonObj) {
	// Add folder image names to image list
	if (jsonObj && (jsonObj.status == 200)) {
		for (var i = 0; i < jsonObj.data.length; i++) {
			this.options.images.push({
				src: this.options.folder + jsonObj.data[i].filename
			});
		}
	}
	
	if ((this.options.images.length > 0) &&
	    (this.imageSize.width > 0) &&
	    (this.imageSize.height > 0))
	{
		// Request images
		for (var i = 0; i < this.options.images.length; i++) {
			var imageOpts = this.options.images[i],
			    imageSpec = {};
			// Set folder-level parameters (if any)
			Object.append(imageSpec, this.options.params);
			// Set 'src' and image-level parameters (if any), minus 'url' and 'server'
			Object.append(imageSpec, imageOpts);
			delete imageSpec.url;
			delete imageSpec.server;
			// Set slideshow-level parameters
			imageSpec.width = this.imageSize.width;
			imageSpec.height = this.imageSize.height;
			imageSpec.autosizefit = 1;
			imageSpec.strip = 1;
            if (!imageSpec.format) imageSpec.format = 'jpg';
			
			var server = imageOpts.server ? imageOpts.server : this.options.server;
			var finalSrc = server + 'image?' + Object.toQueryString(imageSpec);
			this.imageEls.push(
				Asset.image(finalSrc, {
				'data-index': i,
				styles: { 'margin': '0', 'padding': '0', 'vertical-align': 'top' },
				onLoad: this.onImageReady.bind(this)
			}));
		}
	}
	else {
		this.setMessage('');
	}
};

ImgSlideshow.prototype.onImageReady = function(img) {
	// Set the image top margin to vertically centre it.
	// This is more reliable than using vertical-align, especially in IE.
	var topMargin = Math.floor((this.imageSize.height - img.height) / 2);
	img.setStyle('margin-top', topMargin + 'px');

	// Create UI as soon as we have the first image. Async because, if the image
	// is cached locally, this event fires before it has been pushed to this.imageEls[]
	if (img.get('data-index') == 0)
		setTimeout(this.create_ui.bind(this), 1);
};

// Invoked when data and images are ready
ImgSlideshow.prototype.create_ui = function() {
	var wrapperStyles = {
		'border': 'none',
		'display': 'block',
		'width': this.imageSize.width + 'px',
		'height': this.imageSize.height + 'px',
		'margin': '0', 'padding': '0',
		'font-size': '0', 'line-height': '0',
		'position': 'absolute',
		'top': '0px', 'left': '0px',
		'visibility': 'hidden'
	};
	if (this.options.mode == 'stack')
		wrapperStyles['background-color'] = this.options.bgColor;
	
	// Create wrappers for images
	for (var i = 0; i < this.imageEls.length; i++) {
		if (this.options.images[i].url) {
			// Wrap with an <a>
			var wrap = new Element('a', {
				href: this.options.images[i].url,
				styles: wrapperStyles
			});
		}
		else {
			// Wrap with a <div>
			var wrap = new Element('div', {
				styles: wrapperStyles
			});
		}
		wrap.grab(this.imageEls[i]);
		this.wrapEls.push(wrap);
	}
	
	// Add all wrappers to the UI
	this.ctrEl.empty();
	for (var i = 0; i < this.wrapEls.length; i++) {
		this.ctrEl.grab(this.wrapEls[i]);
	}
	// Add arrow controls
	if (this.arrowEls.length === 2) {
		this.arrowEls[0].setStyles({ left: '10px' });
		this.arrowEls[1].setStyles({ right: '10px' });
		this.ctrEl.grab(this.arrowEls[0]);
		this.ctrEl.grab(this.arrowEls[1]);
	}
	// Add dots
	if (this.options.dots) {
		var dotsEl = new Element('div', {
			styles: {
				'position': 'absolute',
				'width': '100%',
				'height': '20px',
				'line-height': '20px',
				'text-align': 'center',
				'z-index': '10',
				'font-family': 'sans-serif',  /* \/ Hope default font supports unicode */
				'font-size': '20px',
				'left': '0px',
				'bottom': '5px'
			}
		});
		for (var i = 0; i < this.wrapEls.length; i++) {
			dotsEl.grab(new Element('a', {
				href: '#',
				html: '&#9679;',  /* Solid circle /\ */
				'data-index': i,
				'class': '_sls_dot',
				styles: {
					'margin': '0 8px 0 8px',
					'text-decoration': 'none',
					'border': 'none'
				},
				events: {
					'click': function(ci, self) {
						return function() { return this.index(ci); }.bind(self);
					}(i, this)
				}
			}));
		}
		this.ctrEl.grab(dotsEl);
	}
	
	// Show first image
	this.wrapEls[0].setStyle('visibility', 'visible');
	this._select_dot(0);
	
	// Install mouse hover pausing
	if (this.options.pauseOnHover) {
		this.ctrEl.addEvent('mouseenter', this._hover_in_fn);
		this.ctrEl.addEvent('mouseleave', this._hover_out_fn);
	}
	// Install page visibility API pausing
	if (this.pvAPI) {
		document.addEventListener('visibilitychange', this._visibility_change_fn, false);
	}
	
	// Start animation
	this.ready = true;
	this.start();
};

// Starts automatic animation
ImgSlideshow.prototype.start = function() {
	if (!this.running && (this.wrapEls.length > 1)) {
		this.direction = 1;
		this.running = true;
		this._animate_async();
	}
	return false;
};

// Stops automatic animation
ImgSlideshow.prototype.stop = function() {
	if (this.animTimer !== null) {
		clearTimeout(this.animTimer);
		this.animTimer = null;
	}
	this.running = false;
	return false;
};

// Manually animate to the previous image
ImgSlideshow.prototype.prev = function() {
	if (this.ready && (this.wrapEls.length > 1) && !this.animating) {
		this.stop();
		this.direction = -1;
		this._animate();
	}
	return false;
};

// Manually animate to the next image
ImgSlideshow.prototype.next = function() {
	if (this.ready && (this.wrapEls.length > 1) && !this.animating) {
		this.stop();
		this.direction = 1;
		this._animate();
	}
	return false;
};

// Manually animate to the image at an index
ImgSlideshow.prototype.index = function(idx) {
	idx = Math.min(Math.max(idx, 0), this.wrapEls.length - 1);
	if (this.ready && (this.wrapEls.length > 1) && !this.animating) {
		this.stop();
		this.direction = (idx >= this.imageIdx) ? 1 : -1;
		this._animate(idx);
	}
	return false;
};

// Note: toIdx is optional
ImgSlideshow.prototype._animate = function(toIdx) {
	switch (this.options.mode) {
		case 'slide': return this._slide(toIdx);
		case 'stack': return this._stack(toIdx);
		case 'fade':  return this._xfade(toIdx);
	}
};

ImgSlideshow.prototype._animate_async = function() {
	if (this.animTimer === null) {
		this.animTimer = setTimeout(
			function() {
				this._animate();
				this.animTimer = null;
			}.bind(this),
			this.options.delay * 1000
		);
	}
};

ImgSlideshow.prototype._slide = function(toIdx) {
	this._do_slide(false, toIdx);
};
ImgSlideshow.prototype._stack = function(toIdx) {
	this._do_slide(true, toIdx);
};

ImgSlideshow.prototype._do_slide = function(stack, toIdx) {
	var curIdx = this.imageIdx,
	    maxIdx = this.wrapEls.length - 1,
	    nextIdx = (toIdx !== undefined) ? toIdx : curIdx + this.direction;
	
	if (nextIdx < 0) nextIdx = maxIdx;
	else if (nextIdx > maxIdx) nextIdx = 0;
	if (nextIdx === curIdx) return;
	
	// Move current image to back of z order (for stack mode)
	this.wrapEls[curIdx].setStyle('z-index', '0');
	// Move next image over to the right (dir 1) / left (dir -1), show it (out of view)
	this.wrapEls[nextIdx].setStyles({
		'left': (this.imageSize.width * this.direction) + 'px',
		'visibility': 'visible',
		'z-index': '1'
	});
	// Now animate current image out, next image in
	this.animating = true;
	new Fx.Elements(
		[this.wrapEls[curIdx], this.wrapEls[nextIdx]], {
			fps: this.options.fps,
			duration: this.options.duration,
		    transition: this.options.transition,
			onComplete: function() {
				this.animating = false;
		    	this.wrapEls[curIdx].setStyle('visibility', 'hidden');
		    	if (this.running)
			    	this._animate_async();
		    }.bind(this)
		}
	).start({
		0: stack ? {} : { 'left': [0, -this.imageSize.width * this.direction] },
		1: { 'left': [this.imageSize.width * this.direction, 0] }
	});
	this.imageIdx = nextIdx;
	this._select_dot(this.imageIdx);
};

ImgSlideshow.prototype._xfade = function(toIdx) {
	var curIdx = this.imageIdx,
	    maxIdx = this.wrapEls.length - 1,
	    nextIdx = (toIdx !== undefined) ? toIdx : curIdx + this.direction;
	
	if (nextIdx < 0) nextIdx = maxIdx;
	else if (nextIdx > maxIdx) nextIdx = 0;
	if (nextIdx === curIdx) return;
	
	// Prep the next image
	this.wrapEls[nextIdx].setStyles({
		'opacity': 0,
		'visibility': 'visible'
	});
	// Now animate current image out, next image in
	this.animating = true;
	new Fx.Elements(
		[this.wrapEls[curIdx], this.wrapEls[nextIdx]], {
			fps: this.options.fps,
			duration: this.options.duration,
		    transition: this.options.transition,
			onComplete: function() {
				this.animating = false;
		    	this.wrapEls[curIdx].setStyle('visibility', 'hidden');
		    	if (this.running)
			    	this._animate_async();
		    }.bind(this)
		}
	).start({
		0: { 'opacity': [1, 0] },
		1: { 'opacity': [0, 1] }
	});
	this.imageIdx = nextIdx;
	this._select_dot(this.imageIdx);
};

ImgSlideshow.prototype._select_dot = function(idx) {
	if (this.options.dots) {
		this.ctrEl.getElements('._sls_dot').each(function(el) {
			el.setStyle('color', (el.get('data-index') == idx) ? this.options.dotSelectedColor : this.options.dotColor);
		}.bind(this));
	}
};

ImgSlideshow.prototype._add_slash = function(str) {
	if (str && str.charAt(str.length - 1) != '/')
		return str + '/';
	else
		return str;
};

ImgSlideshow.prototype._hover_in = function() {
	this.wasRunning = this.running;
	if (this.running)
		this.stop();
};

ImgSlideshow.prototype._hover_out = function() {
	if (this.wasRunning)
		this.start();
};

ImgSlideshow.prototype._visibility_change = function() {
	(document.hidden ? this._hover_in : this._hover_out).bind(this)();
};

/**** Public interface ****/

/* Creates and starts an image slideshow inside the element
 * or element with ID 'container'. The 'options' parameter is required,
 * and defines the folder and/or images to display, and the slideshow options.
 * 
 * Required options:
 * 
 * mode   - One value from: 'slide', 'stack', or 'fade'.
 * server - The base URL of the image server.
 * images - An array of image objects to display in the slideshow, or
 * folder - The relative path of a folder containing images to display.
 * 
 * Optional:
 * 
 * controls - Whether to show left/right arrow controls. Default true.
 * dots     - Whether to show clickable dot controls. Default true.
 * params  - An object containing image parameters to apply to every image.
 * delay   - The number of seconds to show each slide for.
 * pauseOnHover - Whether to pause when the mouse cursor is over the image.
 *                Default true.
 * bgColor - In 'stack' mode, an optional image background colour.
 * 
 * E.g. { mode:   'slide',
 *        server: 'http://images.mycompany.com/',
 *        folder: 'myimages/featured/',
 *        params: { tmp: 'slideshow', angle: 45 }
 *      }
 * E.g. { mode:   'fade',
 *        delay:  7.5,
 *        server: 'http://images.mycompany.com/',
 *        images: [
 *            { src: 'myimages/image1.jpg', url: 'http://www.google.com/' },
 *            { src: 'myimages/image2.jpg', url: 'http://www.bing.com/', left: 0.2, right: 0.8 }
 *        ]
 *      }
 * 
 * When providing an array of images,
 * the following properties are supported for each entry:
 * 
 * src     - Required. The relative path of the image.
 * url     - Optional. A URL to follow when the image is clicked.
 * server  - Optional. An override for the main server value (not usually required).
 * [other] - Optional. Any other properties are added to the src as additional image
 *                     parameters. E.g. tmp, angle, flip, top, left, ...
 */
function slideshow_view_init(container, options) {
	container = document.id(container);
	if (container) {
		// Destroy previous slideshow
		if (container._show != undefined)
			container._show.destroy();
		// Assign new slideshow
		var show = new ImgSlideshow(container, options);
		show.init();
		container._show = show;
	}
	return false;
}

/* Stops a slideshow, or switches it to manual navigation.
 */
function slideshow_view_stop(container) {
	container = document.id(container);
	if (container && container._show)
		return container._show.stop();
}

/* Re-starts a stopped slideshow.
 * Slideshows start automatically when created.
 */
function slideshow_view_start(container) {
	container = document.id(container);
	if (container && container._show)
		return container._show.start();
}

/* Manually moves a slideshow one image to the left.
 */
function slideshow_view_prev(container) {
	container = document.id(container);
	if (container && container._show)
		return container._show.prev();
}

/* Manually moves a slideshow one image to the right.
 */
function slideshow_view_next(container) {
	container = document.id(container);
	if (container && container._show)
		return container._show.next();
}

/* Manually moves a slideshow to an exact image index.
 */
function slideshow_view_index(container, index) {
	container = document.id(container);
	if (container && container._show)
		return container._show.index(index);
}
