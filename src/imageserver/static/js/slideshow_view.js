/*!
	Document:      slideshow_view.js
	Date started:  05 Feb 2013
	By:            Matt Fozard
	Purpose:       Quru Image Server image slideshow library
	Requires:      common_view.js
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
    03Oct2017  Matt  Remove MooTools, remove JSONP, removed fps option
*/

// Easing Equations v1.5 (c) Robert Penner 2001, BSD licensed
// t: current time, b: beginning value, c: change in position, d: duration
// t and d can be in frames or seconds/milliseconds
Math.easeInOutQuad = function(t, b, c, d) {
    if ((t/=d/2) < 1) return c/2*t*t + b;
    return -c/2 * ((--t)*(t-2) - 1) + b;
}

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
		duration: 1000,
		bgColor: 'white',
		easeFn: Math.easeInOutQuad
	};
	// Apply options
	if (userOpts != undefined) {
		this.options = QU.merge(this.options, userOpts);
	}
	
	// Normalise servers and folders
	this.options.server = this._add_slash(this.options.server);
	this.options.folder = this._add_slash(this.options.folder);
	this.options.images.forEach(function (im) {
		if (im.server) im.server = this._add_slash(im.server);
	}.bind(this));
	
	this.imageSize = {
		width: 0,
		height: 0
	};
	
	this.ctrEl = QU.id(container);
	this._hover_in_fn = this._hover_in.bind(this);
	this._hover_out_fn = this._hover_out.bind(this);
	this._visibility_change_fn = this._visibility_change.bind(this);
	this.pvAPI = (document.hidden !== undefined);
    this.dotEls = [];
	this.arrowEls = [];
	this.imageEls = [];
	this.wrapEls = [];
	this.animTimer = null;
	this.ready = false;
	this.running = false;
	this.animating = false;
	this.animator = new ElementAnimation(this.options.duration, this.options.easeFn);
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

	// Preload arrow controls before loading the images
	if (this.options.controls) {
		var arrImgs = ['arrow-left.png', 'arrow-right.png'],
		    arrEvents = [this.prev.bind(this), this.next.bind(this)];
		for (var i = 0; i < arrImgs.length; i++) {
			var arrow = document.createElement('a');
			arrow.href = '#';
			arrow.innerHTML = '<img src="' + this.options.server + 'static/images/slideshow/' + arrImgs[i] + '"> ';  // Trailing space for IE7 hasLayout
			QU.elSetStyles(arrow, {
				position: 'absolute',
				zIndex: '10',
				textDecoration: 'none',
				border: 'none'
			});
			arrow._onclick = arrEvents[i];
			arrow.addEventListener('click', arrow._onclick, false);
			this.arrowEls[i] = arrow;
		}
	}
};

// Free up object handles
ImgSlideshow.prototype.destroy = function() {
	if (this.pvAPI) {
		document.removeEventListener('visibilitychange', this._visibility_change_fn, false);
	}
	if (this.options.pauseOnHover) {
		this.ctrEl.removeEventListener('mouseenter', this._hover_in_fn, false);
		this.ctrEl.removeEventListener('mouseleave', this._hover_out_fn, false);
	}
	this.stop();
	this.ready = false;
	var uiLists = [this.dotEls, this.arrowEls, this.imageEls, this.wrapEls];
	uiLists.forEach(function(list) {
	    list.forEach(function(el) {
	        if (el._onclick) el.removeEventListener('click', el._onclick, false);
	        if (el._onload) el.removeEventListener('load', el._onload, false);
	        QU.elRemove(el);
	    });
	    list.length = 0;
	});
	QU.elClear(this.ctrEl);
};

// Reads the current size/position of the container element,
// and sets some necessary styles to it
ImgSlideshow.prototype.layout = function() {
	// Get container size
	var ctrSize = QU.elInnerSize(this.ctrEl, false);
	// Set image sizes
	this.imageSize.width = ctrSize.width;
	this.imageSize.height = ctrSize.height;
	// Set required container styles
	QU.elSetStyles(this.ctrEl, {
		position: 'relative',  // So that child elements can be positioned absolutely
		overflow: 'hidden',
		textAlign: 'center',
		lineHeight: ctrSize.height + 'px'
	});
};

ImgSlideshow.prototype.setMessage = function(msg) {
	this.ctrEl.innerHTML = '<span style="font-size: small">' + msg + '</span>';
};

ImgSlideshow.prototype.addFolderImages = function() {
	var dataURL = this.options.server + 'api/v1/list/?path=' + encodeURIComponent(this.options.folder);
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
		    var imgData = jsonObj.data[i];
		    if (imgData.supported) {
		        this.options.images.push({
		            src: this.options.folder + imgData.filename
		        });
		    }
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
			imageSpec = QU.merge(imageSpec, this.options.params);
			// Set 'src' and image-level parameters (if any), minus 'url' and 'server'
			imageSpec = QU.merge(imageSpec, imageOpts);
			delete imageSpec.url;
			delete imageSpec.server;
			// Set slideshow-level parameters
			imageSpec.width = this.imageSize.width;
			imageSpec.height = this.imageSize.height;
			imageSpec.autosizefit = 1;
			imageSpec.strip = 1;
            if (!imageSpec.format) imageSpec.format = 'jpg';
			
			var server = imageOpts.server ? imageOpts.server : this.options.server;
			var finalSrc = server + 'image?' + QU.ObjectToQueryString(imageSpec);
			var imageEl = document.createElement('img');
			imageEl._onload = this.onImageReady.bind(this);
			imageEl.addEventListener('load', imageEl._onload, false);
			imageEl.setAttribute('data-index', i);
			imageEl.src = finalSrc;
			imageEl.style.margin = '0';
			imageEl.style.padding = '0';
			imageEl.style.verticalAlign = 'top';
			this.imageEls.push(imageEl);
		}
	}
	else {
		this.setMessage('');
	}
};

ImgSlideshow.prototype.onImageReady = function(e) {
    var img = e.target;
	// Set the image top margin to vertically centre it.
	// This is more reliable than using vertical-align, especially in IE.
	var topMargin = Math.floor((this.imageSize.height - img.height) / 2);
	img.style.marginTop = topMargin + 'px';

	// Create UI as soon as we have the first image. Async because, if the image
	// is cached locally, this event fires before it has been pushed to this.imageEls[]
	if (img.getAttribute('data-index') === '0')
		setTimeout(this.create_ui.bind(this), 1);
};

// Invoked when data and images are ready
ImgSlideshow.prototype.create_ui = function() {
	var wrapperStyles = {
		'border': 'none',
		'display': 'block',
		'width': this.imageSize.width + 'px',
		'height': this.imageSize.height + 'px',
		'margin': '0',
		'padding': '0',
		'fontSize': '0',
		'lineHeight': '0',
		'position': 'absolute',
		'top': '0px',
		'left': '0px',
		'visibility': 'hidden'
	};
	if (this.options.mode === 'stack')
		wrapperStyles['backgroundColor'] = this.options.bgColor;
	
	// Create wrappers for images
	for (var i = 0; i < this.imageEls.length; i++) {
		if (this.options.images[i].url) {
			// Wrap with an <a>
			var wrap = document.createElement('a');
			wrap.href = this.options.images[i].url;
		}
		else {
			// Wrap with a <div>
		    var wrap = document.createElement('div');
		}
        QU.elSetStyles(wrap, wrapperStyles);
		wrap.appendChild(this.imageEls[i]);
		this.wrapEls.push(wrap);
	}
	
	// Add all wrappers to the UI
	QU.elClear(this.ctrEl);
	for (var i = 0; i < this.wrapEls.length; i++) {
		this.ctrEl.appendChild(this.wrapEls[i]);
	}
	// Add arrow controls
	if (this.arrowEls.length === 2) {
		this.arrowEls[0].style.left = '10px';
		this.arrowEls[1].style.right = '10px';
		this.ctrEl.appendChild(this.arrowEls[0]);
		this.ctrEl.appendChild(this.arrowEls[1]);
	}
	// Add dot controls
	if (this.options.dots) {
		var dotsCtr = document.createElement('div');
		QU.elSetStyles(dotsCtr, {
			position: 'absolute',
			width: '100%',
			height: '20px',
			lineHeight: '20px',
			textAlign: 'center',
			zIndex: '10',
			fontFamily: 'sans-serif',   /* \/ Hope default font supports unicode */
			fontSize: '20px',
			left: '0px',
			bottom: '5px'
		});
		for (var i = 0; i < this.wrapEls.length; i++) {
			var dot = document.createElement('a');
			dot.href = '#';
			dot.innerHTML = '&#9679;';  /* Solid circle /\ */
			dot.className = '_sls_dot';
			dot.setAttribute('data-index', i);
			dot.style.margin = '0 8px 0 8px';
			dot.style.textDecoration = 'none';
			dot.style.border = 'none';
			dot._onclick = function(ci, self) { return function(e) { e.preventDefault(); return this.index(ci); }.bind(self); }(i, this);
			dot.addEventListener('click', dot._onclick, false);
			this.dotEls.push(dot);
			dotsCtr.appendChild(dot);
		}
		this.ctrEl.appendChild(dotsCtr);
	}
	
	// Show first image
	this.wrapEls[0].style.visibility = 'visible';
	this._select_dot(0);
	
	// Install mouse hover pausing
	if (this.options.pauseOnHover) {
		this.ctrEl.addEventListener('mouseenter', this._hover_in_fn, false);
		this.ctrEl.addEventListener('mouseleave', this._hover_out_fn, false);
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
ImgSlideshow.prototype.prev = function(e) {
    if (e) e.preventDefault();
	if (this.ready && (this.wrapEls.length > 1) && !this.animating) {
		this.stop();
		this.direction = -1;
		this._animate();
	}
	return false;
};

// Manually animate to the next image
ImgSlideshow.prototype.next = function(e) {
    if (e) e.preventDefault();
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
	this.wrapEls[curIdx].style.zIndex = '0';
	// Move next image over to the right (dir 1) / left (dir -1), show it (out of view)
	this.wrapEls[nextIdx].style.left = (this.imageSize.width * this.direction) + 'px';
	this.wrapEls[nextIdx].style.visibility = 'visible';
	this.wrapEls[nextIdx].style.zIndex = '1';

	// Now animate current image out, next image in
	this.animating = true;
	this.animator.start([
	    { element: this.wrapEls[curIdx], changes: stack ? [] : [{property: 'left', start: 0, end: (-this.imageSize.width * this.direction), unit: 'px'}]},
        { element: this.wrapEls[nextIdx], changes: [{property: 'left', start: (this.imageSize.width * this.direction), end: 0, unit: 'px'}]},
	], function() {
	    // On complete
        this.animating = false;
        this.wrapEls[curIdx].style.visibility = 'hidden';
        if (this.running)
            this._animate_async();
    }.bind(this));

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
	this.wrapEls[nextIdx].style.opacity = '0';
	this.wrapEls[nextIdx].style.visibility = 'visible';

	// Now animate current image out, next image in
	this.animating = true;
    this.animator.start([
        { element: this.wrapEls[curIdx], changes: [{property: 'opacity', start: 1, end: 0, unit: ''}]},
        { element: this.wrapEls[nextIdx], changes: [{property: 'opacity', start: 0, end: 1, unit: ''}]},
    ], function() {
        // On complete
        this.animating = false;
        this.wrapEls[curIdx].style.visibility = 'hidden';
        if (this.running)
            this._animate_async();
    }.bind(this));

	this.imageIdx = nextIdx;
	this._select_dot(this.imageIdx);
};

ImgSlideshow.prototype._select_dot = function(idx) {
	if (this.options.dots) {
		for (var i = 0; i < this.dotEls.length; i++) {
		    var el = this.dotEls[i];
			el.style.color = (el.getAttribute('data-index') === ''+idx) ? this.options.dotSelectedColor : this.options.dotColor;
		}
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
    // Stop the animation when the web page is hidden
    (document.hidden ? this._hover_in : this._hover_out).bind(this)();
};

/**** Element animation utility ****/

// Creates a utility for animating one or more elements, with duration in milliseconds.
// The easing function can be any of the Math.ease() functions defined above.
// This is the IE9 version. In IE10+ you can use CSS classes with CSS transitions
// and hook into the 'transitionend' event.
function ElementAnimation(duration, easeFn) {
    this.steps = Math.round(Math.max(1, duration / 16.66));  // 16.66 == 60fps
    this.easeFn = easeFn;
    this.stepFn = this._step.bind(this);
    if (window.requestAnimationFrame)
        this.animate = function() { window.requestAnimationFrame(this.stepFn); };
    else
        this.animate = function() { return setTimeout(this.stepFn, 17); };
}

// Starts an animation, and optionally sets a callback function for when the
// animation has completed. The spec should be an array of elements and what
// to change about them in the format:
// [
//   { element: el, changes: [
//       {property: 'opacity', start: 0, end: 1, unit: ''},
//       {property: 'marginLeft', start: 100, end: 500, unit: 'px'}
//     ]
//   },
//   { ...next element... }
// ]
// Only numeric properties can be animated.
ElementAnimation.prototype.start = function(spec, onCompleteFn) {
    spec.forEach(function(elSpec) {
        elSpec.changes.forEach(function(ch) {
            ch.diff = ch.end - ch.start;
        });
    });
    this.spec = spec;
    this.onCompleteFn = onCompleteFn;
    this.step = 0;
    this.animate();
}

ElementAnimation.prototype._step = function() {
    var elSpec, propSpec;
    this.step++;
    // Using numeric loops here as it should be a bit faster than repeated forEach function calls
    for (var i = 0; i < this.spec.length; i++) {
        elSpec = this.spec[i];
        for (var j = 0; j < elSpec.changes.length; j++) {
            propSpec = elSpec.changes[j];
            elSpec.element.style[propSpec.property] = this.easeFn(
                this.step, propSpec.start, propSpec.diff, this.steps
            ) + propSpec.unit;
        }
    }
    // Request next frame or complete
    if (this.step < this.steps) {
        this.animate();
    } else if (this.onCompleteFn) {
        this.onCompleteFn();
    }
}

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
 * dotColor - The colour of an unselected dot. Default #666666 (mid grey).
 * dotSelectedColor - The colour of a selected dot. Default #dddddd (light grey).
 * params   - An object containing image parameters to apply to every image.
 * delay    - The number of seconds to show each slide for.
 * duration - The duration of the slide or fade animation in milliseconds. Default 1000.
 * pauseOnHover - Whether to pause when the mouse cursor is over the image. Default true.
 * bgColor  - In 'stack' mode, an optional image background colour.
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
	container = QU.id(container);
	if (container) {
	    if (QU.supported) {
            // Destroy previous slideshow
            if (container._show !== undefined)
                container._show.destroy();
            // Assign new slideshow
            var show = new ImgSlideshow(container, options);
            show.init();
            container._show = show;
	    }
        else {
            container.innerHTML = 'Sorry, this control is unsupported. Try upgrading your web browser.';
        }
	}
	return false;
}

/* Stops a slideshow, or switches it to manual navigation.
 */
function slideshow_view_stop(container) {
	container = QU.id(container);
	if (container && container._show)
		return container._show.stop();
}

/* Re-starts a stopped slideshow.
 * Slideshows start automatically when created.
 */
function slideshow_view_start(container) {
	container = QU.id(container);
	if (container && container._show)
		return container._show.start();
}

/* Manually moves a slideshow one image to the left.
 */
function slideshow_view_prev(container) {
	container = QU.id(container);
	if (container && container._show)
		return container._show.prev();
}

/* Manually moves a slideshow one image to the right.
 */
function slideshow_view_next(container) {
	container = QU.id(container);
	if (container && container._show)
		return container._show.next();
}

/* Manually moves a slideshow to an exact image index.
 */
function slideshow_view_index(container, index) {
	container = QU.id(container);
	if (container && container._show)
		return container._show.index(index);
}
