/*!
	Document:      gallery_view.js
	Date started:  26 July 2013
	By:            Matt Fozard
	Purpose:       Quru Image Server gallery viewer
	Requires:      common_view.js
	               canvas_view.js
	               MooTools Core 1.3 (no compat)
	               MooTools More 1.3 - Element.Measure, Fx.Scroll, Mask,
	               Request.JSONP, String.QueryString, URI
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
	11Oct2013  Matt  Strip halign and valign from all images by default
	11Nov2013  Matt  Add title/description image options, set title on thumbnails
	11Nov2013  Matt  Add events interface
    28Sep2017  Matt  Remove MooTools, remove JSONP
*/

// TODO remove me
// Strips empty query string values from a URL, and converts "+"s to " "s
function _clean_url(url) {
    return url ? url.cleanQueryString().replace(/\+/g, ' ') : url;
}

/**** Private interface ****/

function GalleryView(container, userOpts, events) {
	// Default options
	this.options = {
		server: '',
		folder: '',
		images: [],
		params: {},
		startImage: '',
		thumbsize: { width: 120, height: 120 },
		viewer: {},
		stripaligns: true
	};
	// Apply options
	if (userOpts !== undefined) {
		this.options = Object.merge(this.options, userOpts);
	}
	
	this.events = events;
	
	// Normalise servers and folders
	this.options.server = this._add_slash(this.options.server);
	this.options.folder = this._add_slash(this.options.folder);
	this.options.images.each(function (im) {
		if (im.server) im.server = this._add_slash(im.server);
	}.bind(this));
	
	// Gallery vars
	this.firstIdx = 0;
	this.thumbIdx = -1;
	this.thumbnails = [];
	
	this.touchAttrs = {
		last: { x: 0, y: 0 }
	};
	
	// Get and clear container element
	this.ctrEl = document.id(container);
	this.ctrEl.empty();
	
	this.elements = {};
	this.create_ui();
	this.layout();
}

// Call init first
GalleryView.prototype.init = function() {
	this.setMessage('Loading gallery...');
	if (this.options.folder)
		this.addFolderImages();
	else
		this.onDataReady(null);
};

// Free up object handles
GalleryView.prototype.destroy = function() {
	this.events = null;
	if (this.elements.main_view && this.elements.main_view._viewer)
		this.elements.main_view._viewer.destroy();
	this.ctrEl.empty();
};

GalleryView.prototype.create_ui = function() {
	// Wrapper to apply gallery class
	var wrapper = new Element('div', {
		'class': 'gallery'
	});
	this.ctrEl.grab(wrapper);
	// Canvas view container
	var main_view = new Element('div', {
		'class': 'main_view',
		'styles': {
			'text-align': 'center'
		}
	});
	// Thumbnails container
	var thumbnails = new Element('div', {
		'class': 'thumbnails',
		'styles': {
			overflow: 'hidden',
			position: 'relative'
		}
	});
	wrapper.grab(main_view);
	wrapper.grab(thumbnails);
	
	// Scroll left/right buttons
	var tn_left = new Element('a', {
		'class': 'scroll_button disabled',
		'html': '&lt;',
		'styles': {
			display: 'block',
			position: 'absolute',
			'z-index': '1',
			top: 0,
			left: 0,
			margin: 0
		}
	});
	var tn_right = new Element('a', {
		'class': 'scroll_button disabled',
		'html': '&gt;',
		'styles': {
			display: 'block',
			position: 'absolute',
			'z-index': '1',
			top: 0,
			right: 0,
			margin: 0
		}
	});
	thumbnails.grab(tn_left);
	thumbnails.grab(tn_right);
	
	// Hides the thumbnail list overflow and scroll bars
	var tn_scroller_viewport = new Element('div', {
		'class': 'scroller_viewport',
		'styles': {
			overflow: 'hidden',
			'margin-left': tn_left.getSize().x + 'px'
		}
	});
	// Provides the scroll function via standard scroll bars
	var tn_scrollable = new Element('div', {
		'styles': { overflow: 'auto' }
	});
	// Hosts the thumbnail images in a single long line
	var tn_scroller = new Element('div', {
		'class': 'scroller',
		'styles': {
			position: 'relative',    /* for getting img.offsetLeft */
			'white-space': 'nowrap'
		}
	});
	tn_scrollable.grab(tn_scroller);
	tn_scroller_viewport.grab(tn_scrollable);
	thumbnails.grab(tn_scroller_viewport);

	// Add event handlers
	// Rely on compatibility mode on tablets (tested OK)
	tn_scrollable.addEvent('scroll', function() { this.onThumbsScroll(); }.bind(this));
	tn_left.addEvent('click', function() { this.scrollRelative(-1); return false; }.bind(this));
	tn_right.addEvent('click', function() { this.scrollRelative(1); return false; }.bind(this));

	// Save refs to things we need later
	this.elements = {
		wrapper: wrapper,
		main_view: main_view,
		tn_wrapper: thumbnails,
		tn_viewport: tn_scroller_viewport,
		tn_scrollable: tn_scrollable,
		tn_panel: tn_scroller,
		tn_left: tn_left,
		tn_right: tn_right
	};
	this.scroller = new Fx.Scroll(tn_scrollable, {
		transition: 'sine:in:out',
		duration: 500
	});
};

GalleryView.prototype.layout = function() {
	var ctrSize  = this.ctrEl.getComputedSize(),
	    wrapSize = this.elements.wrapper.getComputedSize({ styles: ['margin','padding','border'] }),
	    tnSize   = this.elements.tn_wrapper.getComputedSize({ styles: ['margin','padding','border'] }),
	    thumbHeight = this.options.thumbsize.height + 12,        // extra for image borders
	    mvHeight = ctrSize.height - (wrapSize.computedTop + wrapSize.computedBottom +
	                   tnSize.computedTop + tnSize.computedBottom + thumbHeight);
	
	// Don't use odd dimensions for the main view
	if (mvHeight % 2 == 1) mvHeight--;
	
	// Set heights
	this.elements.main_view.setStyles({
		height: mvHeight + 'px',
		'line-height': mvHeight + 'px'
	});
	this.elements.tn_wrapper.setStyles({
		height: thumbHeight + 'px',
		'line-height': thumbHeight + 'px'
	});
	this.elements.tn_left.setStyles({
		height: thumbHeight + 'px',
		'line-height': thumbHeight + 'px'
	});
	this.elements.tn_right.setStyles({
		height: thumbHeight + 'px',
		'line-height': thumbHeight + 'px'
	});
	
	var panelWidth = this.elements.tn_wrapper.getSize().x,
	    btnWidth = this.elements.tn_left.getSize().x,
	    tnvpWidth = panelWidth - (2 * btnWidth);
	
	// Set thumbnail area sizing
	this.elements.tn_viewport.setStyles({
		width: tnvpWidth + 'px',
		height: thumbHeight + 'px'
	});	
	this.elements.tn_scrollable.setStyles({
		width: tnvpWidth + 'px'
	});
	this.elements.tn_panel.setStyles({
		height: thumbHeight + 'px',
		'line-height': thumbHeight-4 + 'px'
	});
	
	// Resize canvas viewer
	canvas_view_resize(this.elements.main_view);
};

GalleryView.prototype.setMessage = function(msg) {
	this.elements.main_view.innerHTML = '<span style="font-size: small">' + msg + '</span>';
};

GalleryView.prototype.addFolderImages = function() {
	var dataURL = this.options.server + 'api/v1/list?path=' + encodeURIComponent(this.options.folder);
    QU.jsonRequest(
        dataURL,
        'GET',
        function(xhr, jobj) { this.onDataReady(jobj); }.bind(this),
        function(xhr, msg)  { this.setMessage('');    }.bind(this)
    ).send();
};

GalleryView.prototype.onDataReady = function(jsonObj) {
	// Add folder image names to image list
	if (jsonObj && (jsonObj.status == 200)) {
		for (var i = 0; i < jsonObj.data.length; i++) {
			this.options.images.push({
				src: this.options.folder + jsonObj.data[i].filename
			});
		}
	}
	
	if (this.options.images.length > 0)
	{
		var requests = [],
		    setFirst = false;
		
		// Create thumbnail images
		for (var i = 0; i < this.options.images.length; i++) {
			var imageOpts = this.options.images[i],
			    imageSpec = {};
			// Set folder-level parameters (if any)
			Object.append(imageSpec, this.options.params);
			// Set 'src' and image-level parameters (if any), minus server, title, description
			Object.append(imageSpec, imageOpts);
			delete imageSpec.server;
			delete imageSpec.title;
			delete imageSpec.description;
			// Set thumbnail parameters
			imageSpec.width = this.options.thumbsize.width;
			imageSpec.height = this.options.thumbsize.height;
			imageSpec.strip = 1;
            if (!imageSpec.format) imageSpec.format = 'png';
            if (!imageSpec.fill) imageSpec.fill = 'none';
            // Usually we'll want everything centred
            if (this.options.stripaligns) {
                delete imageSpec.halign;
                delete imageSpec.valign;
            }
			
			var server = imageOpts.server ? imageOpts.server : this.options.server,
			    finalSrc = server + 'image?' + Object.toQueryString(imageSpec);
			
			// De-dup and add the <img>
			if (!requests.contains(finalSrc)) {
				if ((this.options.startImage === imageSpec.src) && !setFirst) {
					this.firstIdx = i;
					setFirst = true; // when >1 match, use the left-most
				}
				requests.push(finalSrc);
				this.addThumbnail(finalSrc, i, imageOpts.title, imageOpts.description);
			}
		}
		this.setScrollButtons();
	}
	else {
		this.setMessage('There are no images to display');
	}
};

GalleryView.prototype.addThumbnail = function(src, idx, title, description) {
	var thumbEl = new Element('img', {
		'src': src,
		'data-index': idx,
		'title': title ? title : '',
		'draggable': 'false'
//      Disabled to prevent stretching of images smaller than the thumbnail size
//		width: this.options.thumbsize.width + 'px'
//		height: this.options.thumbsize.height + 'px'
	});
	if (title) thumbEl.set('data-title', title);
	if (description) thumbEl.set('data-description', description);
	
	this.thumbnails.push(thumbEl);
	this.elements.tn_panel.grab(thumbEl);
	
	// Add event handlers
	// Use proper touch events to avoid phantom thumbnail clicks on tablets
	thumbEl.addEvent('load', function() { this.onThumbLoaded(thumbEl, idx); }.bind(this));
	if ('ontouchstart' in window && window.Touch) {
		thumbEl.addEvent('touchstart', function(e) { this.onThumbTouchStart(e, idx); }.bind(this));
		thumbEl.addEvent('touchend',   function(e) { this.onThumbTouchEnd(e, idx); }.bind(this));
	}
	else {
		thumbEl.addEvent('click', function() { this.onThumbClick(thumbEl, idx); }.bind(this));
	}
};

GalleryView.prototype.onThumbLoaded = function(img, idx) {
	this.setScrollButtons();
	if (this.firstIdx === idx)
		this.moveDirect(idx);
};

GalleryView.prototype.onThumbTouchStart = function(e, idx) {
	if (e.touches.length === 1) {
		this.touchAttrs.last.x = e.touches[0].pageX;
		this.touchAttrs.last.y = e.touches[0].pageY;
	}
	return true;
};

GalleryView.prototype.onThumbTouchEnd = function(e, idx) {
	// Fire click for taps, ignore drags
	if (Math.abs(this.touchAttrs.last.x - e.changedTouches[0].pageX) < 10 &&
	    Math.abs(this.touchAttrs.last.y - e.changedTouches[0].pageY) < 10) {
		this.onThumbClick(e.target, idx);
	}
	return true;
};

GalleryView.prototype.onThumbClick = function(img, idx) {
	this.moveDirect(idx);
};

// Scroll the thumbnail list without changing the selection
GalleryView.prototype.scrollDirect = function(idx, edge) {
	if (this.thumbnails.length) {
		var scrollInfo = this.getScrollInfo(),
		    idx = Math.max(0, Math.min(this.thumbnails.length - 1, idx));
		if (edge === 'left') {
			if (idx > 0) {
			    var thumb = this.thumbnails[idx];
				this.scroller.start(thumb.offsetLeft - scrollInfo.thumbMargin, 0);
			}
			else {
				this.scroller.start(0, 0);
			}
		}
		else { // === 'right'
			if (idx < (this.thumbnails.length - 1)) {
				var nextThumb = this.thumbnails[idx + 1];
				this.scroller.start(nextThumb.offsetLeft - scrollInfo.viewportWidth, 0);
			}
			else {
				this.scroller.start(scrollInfo.scrollTotal - scrollInfo.viewportWidth, 0);
			}
		}
	}
};

// Scroll the thumbnail list without changing the selection
GalleryView.prototype.scrollRelative = function(offset) {
	if (this.thumbnails.length && offset) {
		var scrollInfo = this.getScrollInfo();
		if (offset < 0) {
			if (scrollInfo.scrollFrom > 0)
				this.scrollDirect(scrollInfo.startThumbIdx + offset, 'left');
		}
		else {
			if (scrollInfo.scrollTo < scrollInfo.scrollTotal)
				this.scrollDirect(scrollInfo.endThumbIdx + offset, 'right');
		}
	}
};

// Select a new thumbnail then auto-scroll
GalleryView.prototype.moveRelative = function(offset) {
	if (this.thumbnails.length && offset) {
		this.moveDirect(this.thumbIdx + offset);
	}
};

// Select a new thumbnail then auto-scroll
GalleryView.prototype.moveDirect = function(idx) {
	if (this.thumbnails.length) {
		idx = Math.max(0, Math.min(this.thumbnails.length - 1, idx));
		if (idx !== this.thumbIdx) {
			// Change the selected thumbnail
			this.thumbIdx = idx;
			this.thumbnails.each(function(t) { t.removeClass('selected'); });
			this.thumbnails[idx].addClass('selected');
			// Launch the associated viewer if we don't move anywhere else soon
			if (this.moveTimer !== undefined)
				clearTimeout(this.moveTimer);
			this.moveTimer = setTimeout(this.onMoveComplete.bind(this), 100);
		}
	}
};

GalleryView.prototype.onMoveComplete = function() {
	delete this.moveTimer;
	this.autoThumbScroll();
	
	var thumbImg = this.thumbnails[this.thumbIdx],
	    viewerOpts = Object.clone(this.options.viewer);
	
	if (thumbImg.get('data-title') != null)
		viewerOpts.title = thumbImg.get('data-title');
	if (thumbImg.get('data-description') != null)
		viewerOpts.description = thumbImg.get('data-description');
	
	// Fire change event
	if (this.events)
		ImgUtils.fireEvent(this.events.onchange, this, [this.options.images[this.thumbIdx].src]);
	
	canvas_view_init(
		this.elements.main_view,
		thumbImg.src,
		viewerOpts,
		this.events
	);
};

GalleryView.prototype.onThumbsScroll = function() {
	// Call an event when scrolling has finished
	if (this.scrollTimer !== undefined)
		clearTimeout(this.scrollTimer);
	this.scrollTimer = setTimeout(this.onThumbsScrollComplete.bind(this), 100);
};

GalleryView.prototype.onThumbsScrollComplete = function() {
	delete this.scrollTimer;
	this.setScrollButtons();
	
	if (this.autoScrollIdx !== undefined) {
		if (this.autoScrollIdx !== this.thumbIdx) {
			// The auto-scroll just finished is obsolete and we need to do another
			delete this.autoScrollIdx;
			this.autoThumbScroll();
		}
		else {
			delete this.autoScrollIdx;
		}
	}
};

// Auto-scroll the currently selected thumbnail into view
GalleryView.prototype.autoThumbScroll = function() {
	var idx = this.thumbIdx,
	    scrollInfo = this.getScrollInfo();

	// Async events may change this.thumbIdx while we're auto-scrolling.
	// Try to detect this and kick off another auto-scroll if required.
	if (this.autoScrollIdx === undefined)
		this.autoScrollIdx = idx;

	// If part visible or last thumb in view, auto-scroll one
	if (idx === scrollInfo.startThumbIdx)
		this.scrollRelative(-1);
	else if (idx === scrollInfo.endThumbIdx)
		this.scrollRelative(1);
	// If out of view, auto-scroll many
	else if (idx < scrollInfo.startThumbIdx)
		this.scrollDirect(idx, 'left');
	else if (idx > scrollInfo.endThumbIdx)
		this.scrollDirect(idx, 'right');
	// Already in view
	else
		delete this.autoScrollIdx;
};

GalleryView.prototype.getScrollInfo = function() {
	// Get scroll positions (thumblistEl bit is for IE7)
	var scrollingEl = this.elements.tn_scrollable,
	    thumblistEl = this.elements.tn_panel,
	    viewportEl = scrollingEl.getParent(),
	    scrollPosFrom = scrollingEl.getScroll().x,
	    scrollTotal = Math.max(scrollingEl.getScrollSize().x, thumblistEl.getScrollSize().x),
	    viewportWidth = viewportEl.getSize().x,
	    scrollPosTo = scrollPosFrom + viewportWidth;
	
	// Work out visible thumbnails
	var visFrom = -1, visTo = -1,
	    tWidth = this.thumbnails[0].getSize().x,
	    tMargin = tWidth - this.thumbnails[0].width;
	for (var i = 0; i < this.thumbnails.length; i++) {
		var t = this.thumbnails[i],
		    notVisible = ((t.offsetLeft + tWidth) <= scrollPosFrom) || (t.offsetLeft >= scrollPosTo);
		if (!notVisible) {
			if (visFrom == -1) visFrom = i;
			visTo = Math.max(visTo, i);
		}
		if (notVisible && (visTo != -1)) break;
	}
	return {
		scrollFrom: scrollPosFrom,
		scrollTo: scrollPosTo,
		scrollTotal: scrollTotal,
		viewportWidth: viewportWidth,
		thumbMargin: tMargin,
		startThumbIdx: visFrom,
		endThumbIdx: visTo
	};
};

GalleryView.prototype.setScrollButtons = function() {
	// Auto enable/disable the scroll buttons
	var scrollInfo = this.getScrollInfo();
	if (scrollInfo.scrollFrom <= 0)
		this.elements.tn_left.addClass('disabled');
	else
		this.elements.tn_left.removeClass('disabled');
	if (scrollInfo.scrollTo >= scrollInfo.scrollTotal)
		this.elements.tn_right.addClass('disabled');
	else
		this.elements.tn_right.removeClass('disabled');
};

GalleryView.prototype._add_slash = function(str) {
	if (str && str.charAt(str.length - 1) != '/')
		return str + '/';
	else
		return str;
};

/**** Full screen mode ****/

function GalleryViewMask(options, events) {
	this.options = options;
	this.events = events;
	// Don't allow image to go full-screen while we are
	// This also prevents duplicate fullscreen events
	if (!this.options) this.options = {};
	if (!this.options.viewer) this.options.viewer = {};
	if (!this.options.viewer.controls) this.options.viewer.controls = {};
	this.options.viewer.controls.fullscreen = false;
	
	this.fullScreenFixed = true;
	this.animating = false;
	this.ctrEl = null;
	this.mask = null;
	
	this.fullKeydownFn = function(e) { this.fullscreenKeydown(e); }.bind(this);
	this.fullResizeFn = function(e) { this.fullscreenResize(e); }.bind(this);
}

GalleryViewMask.prototype.open = function() {
	var fsCoords = this.fullscreenGetCoords();
	// Mask the page
	this.mask = new PageMask(
	    'fullscreen_mask', // In canvas_view.css
	    { 'zIndex': '1000' },
	    function(mask) { this.close(); }.bind(this)
	);
	this.mask.show();
	// Add a gallery container
	this.ctrEl = new Element('div', {
		'class': 'fullscreen',
		styles: {
			position: this.fullScreenFixed ? 'fixed' : 'absolute',
			'z-index': '1001',
			opacity: '0',
			left: fsCoords.left + 'px',
			top: fsCoords.top + 'px',
			width: fsCoords.width + 'px',
			height: fsCoords.height + 'px',
			margin: '0',
			padding: '0'
	}});
	document.id(document.body).grab(this.ctrEl, 'top');
	// Create a close button to put on top of the canvas_view
	var closeEl = new Element('a', {
		'class': 'close_button',
		styles: {
			display: 'block', position: 'absolute',
			'z-index': '1102',    /* same as canvas_view alert panel */
			top: '0px', right: '0px', width: '33px', height: '33px'
		},
		events: {
			click: this.close.bind(this)
		}
	});
	
	// Add event handlers
	window.addEvent('keydown', this.fullKeydownFn);
	window.addEvent('resize', this.fullResizeFn);
	// Create the gallery
	gallery_view_init(this.ctrEl, this.options, this.events);
	this.ctrEl.getElement('.gallery').grab(closeEl, 'top');
	// Fade in container
	new Fx.Tween(this.ctrEl, { duration: 500 }).start('opacity', 0, 1);
	// Fire fullscreen event
	if (this.events)
		ImgUtils.fireEvent(this.events.onfullscreen, this.ctrEl._gallery, ['', true]);
};

GalleryViewMask.prototype.close = function() {
	// Ignore double-clicks (only affects fade-out)
	if (this.animating)
		return;
	// Fade out gallery then close down
	this.animating = true;
	new Fx.Tween(this.ctrEl, {
		duration: 300,
		onComplete: function() {
			// Fire fullscreen event before destroying the gallery
			if (this.events)
				ImgUtils.fireEvent(this.events.onfullscreen, this.ctrEl._gallery, ['', false]);
			// Remove event handlers
			window.removeEvent('resize', this.fullResizeFn);
			window.removeEvent('keydown', this.fullKeydownFn);
			// Destroy gallery
			if (this.ctrEl._gallery)
				this.ctrEl._gallery.destroy();
			// Take container back out of the page
			this.ctrEl.dispose();
			this.ctrEl = null;
			// Hide mask
			this.mask.destroy();
			this.mask = null;
			
			this.animating = false;			
		}.bind(this)
	}).start('opacity', 1, 0);
};

GalleryViewMask.prototype.fullscreenKeydown = function(e) {
	switch (e.code) {
		case 27:
			// Close async because we don't want to be in here when this handler gets removed
			e.stop();
			setTimeout(this.close.bind(this), 1);
			break;
		case 37:
		case 40:
			e.stop();
			if (this.ctrEl._gallery) this.ctrEl._gallery.moveRelative(-1);
			break;
		case 39:
		case 38:
			e.stop();
			if (this.ctrEl._gallery) this.ctrEl._gallery.moveRelative(1);
			break;
	}
}

GalleryViewMask.prototype.fullscreenResize = function(e) {
	// The mask resizes itself.
	// We must resize the viewer container.
	var fsCoords = this.fullscreenGetCoords();
	this.ctrEl.setStyles({
		left: fsCoords.left + 'px',
		top: fsCoords.top + 'px',
		width: fsCoords.width + 'px',
		height: fsCoords.height + 'px'
	});
	if (this.ctrEl._gallery)
		this.ctrEl._gallery.layout();
};

GalleryViewMask.prototype.fullscreenGetCoords = function() {
	// Get browser total viewport size
	// #517 Prefer window.inner* to get the visual viewport in mobile browsers
	//      http://www.quirksmode.org/mobile/viewports2.html "Measuring the visual viewport"
	var winSize   = window.innerWidth ? { x: window.innerWidth, y: window.innerHeight } : window.getSize(),
	    winScroll = this.fullScreenFixed ? { x: 0, y: 0 } : window.getScroll(),
	    winMargin = Math.min(Math.round(winSize.x / 40), Math.round(winSize.y / 40));
	// Get target placement of container element
	var tgtLeft   = (winScroll.x + winMargin),
	    tgtTop    = (winScroll.y + winMargin),
	    tgtWidth  = (winSize.x - (2 * winMargin)),
	    tgtHeight = (winSize.y - (2 * winMargin));
	return {
		left: tgtLeft,
		top: tgtTop,
		// Enforce some minimum size
		width: Math.max(tgtWidth, 250),
		height: Math.max(tgtHeight, 250)
	};
};

/**** Public interface ****/

/* Creates an image gallery inside the element or element with ID 'container'.
 * The 'options' parameter is required, and defines the folder and/or images to
 * display, and the gallery options.
 * The 'events' parameter is optional, and includes all the events supported by
 * the canvas viewer, plus those listed below.
 * 
 * Required options:
 * 
 * server - The base URL of the image server.
 * images - An array of image objects to display in the gallery, or
 * folder - The relative path of a folder containing images to display.
 * 
 * Optional:
 * 
 * thumbsize - An object containing width and height attributes that sets the
 *             thumbnail image size. Default size 150x150 pixels.
 * startImage - The relative path to the gallery image to select first.
 * params  - An object containing image parameters to apply to every image.
 * viewer  - An object containing options to apply to the main image viewer.
 *           See the canvas_view file for the available viewer options.
 * 
 * E.g. { server: 'http://images.mycompany.com/',
 *        folder: 'myimages/featured/',
 *        startImage: 'myimages/image1.jpg',
 *        params: { tmp: 'gallery', quality: 80 },
 *        viewer: { showcontrols: 'no' }
 *      }
 * E.g. { server: 'http://images.mycompany.com/',
 *        thumbsize: { width: 150, height: 150 },
 *        images: [
 *            { src: 'myimages/image1.jpg', tmp: 'gallery' },
 *            { src: 'myimages/image2.jpg', tmp: 'gallery', left: 0.2, right: 0.8 }
 *            { src: 'myimages/image3.jpg', tmp: 'gallery', title: 'The Empire State building, 1979' },
 *        ]
 *      }
 * 
 * When providing an array of images,
 * the following properties are supported for each entry:
 * 
 * src     - Required. The relative path of the image.
 * server  - Optional. An override for the main server value (not usually required).
 * title       - Optional. Overrides the image's default title in the control panel.
 * description - Optional. Overrides the image's default description in the control panel.
 * [other] - Optional. Any other properties are added to the src as additional image
 *                     parameters. E.g. tmp, angle, flip, top, left, ...
 *
 * Available events:
 * 
 * onchange - function(src) - fires when a new image is selected
 * 
 * Plus the other events provided by the canvas viewer:
 *   onload, oninfo, ondownload, onfullscreen.
 */
function gallery_view_init(container, options, events) {
	container = document.id(container);
	if (container) {
		var gallery = new GalleryView(container, options, events);
		gallery.init();
		container._gallery = gallery;
	}
	return false;
}

/* Notifies the gallery that its container has been resized
 */
function gallery_view_resize(container) {
	container = document.id(container);
	if (container && container._gallery)
		container._gallery.layout();
	return false;
}

/* Converts an existing element (or element ID) to launch a full screen gallery
 * viewer on click. See gallery_view_init for the required and available options
 * and events.
 */
function gallery_view_init_fullscreen(element, options, events) {
	element = document.id(element);
	if (element) {
		// Modify a copy of the supplied options!
		var opts = options ? Object.clone(options) : {};
		
		element.removeEvents('click');
		element.addEvent('click', function() {
			// Try to default the start image if it's not set
			if (!opts.startImage) {
				var imageURL = ImgUtils.getImageSrc(element);
				if (imageURL) {
					var parsedURL = new URI(_clean_url(imageURL)),
					    srcParam = parsedURL.getData('src');
					if (srcParam)
						opts.startImage = srcParam;
				}
			}
			(new GalleryViewMask(opts, events)).open();
		});
	}
	return false;
}

/* Finds all existing image elements having class 'className', and converts
 * them to launch a full screen gallery viewer on click. The gallery will
 * contain all matched images, in addition to any that are specified in the
 * supplied options.
 * 
 * The options parameter is optional, see gallery_view_init for info.
 * If no options are given, the server name and images to display are
 * determined automatically from the matched images.
 * 
 * The events parameter is optional, see gallery_view_init for info.
 */
function gallery_view_init_all_fullscreen(className, options, events) {
	var elements = $$('.' + className);
	if (elements.length > 0) {
		var options = options || {};
		options.images = options.images || [];
		// Generate options and image list from elements
		elements.each(function(element) {
			var imageURL = ImgUtils.getImageSrc(element);
			if (imageURL) {
				var parsedURL = new URI(_clean_url(imageURL)),
				    srcParam = parsedURL.getData('src');
				if (srcParam) {
					// This looks like an image server image
					var host = parsedURL.get('host') || '/',
					    scheme = parsedURL.get('scheme') || '//',
					    port = parsedURL.get('port');

					// Get the server base URL for this image
					if (host != '/') {
						var server_url = scheme;
						if (scheme != '//') server_url += '://';
						server_url += host;
						if ((port != '80') && (port != '443')) server_url += ':'+port;
						server_url += '/';
					}
					else {
						var server_url = host;
					}
					
					// Use any img title/alt as the image title
					var imageTitle = element.title || element.alt;
					
					// Add this image to the image list
					var imageSpec = { server: server_url };
					if (imageTitle) imageSpec.title = imageTitle;
					Object.append(imageSpec, parsedURL.getData());
					options.images.push(imageSpec);

					if (!options.server) {
						options.server = server_url;
					}
				}
			}
		});
		// Set the click handlers for elements
		if (options.images.length > 0) {
			elements.each(function(el) {
				gallery_view_init_fullscreen(el, options, events);
			});
		}
	}
	return false;
}
