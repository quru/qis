/*!
	Document:      simple_view.js
	Date started:  13 May 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server simple viewer client
	Requires:      MooTools Core 1.3 (no compat)
	               MooTools More 1.3 - Element.Measure, String.QueryString
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

	Last Changed:  $Date$ $Rev$ by $Author$
	
	Notable modifications:
	Date       By    Details
	=========  ====  ============================================================
	09Jun2011  Matt  Allow simple_view_init to be called multiple times to 
	                 change the image
	12Jul2011  Matt  Bug fix to handle + escaped URLs
	14Jul2011  Matt  Add interface to zoom-enable an existing image element
	24Jan2012  Matt  Do not zoom images smaller than the viewport
*/

/**** Private imaging class ****/

function ImgSimpleView(container, imageEl, imageURL) {
	// Get container info
	this.containerEl   = document.id(container);
	this.containerSize = this.containerEl.getComputedSize(); // Prefer client area, excl. borders+padding
	if ((this.containerSize.width == 0) && (this.containerSize.height == 0))
		this.containerSize = { width: this.containerEl.clientWidth, height: this.containerEl.clientHeight };
	// Parse the URL
	if (imageEl && (imageURL == null))
		imageURL = imageEl.src;
	imageURL = imageURL.cleanQueryString().replace(/\+/g, ' ');
	var urlSep = imageURL.indexOf('?');
	this.baseURL = imageURL.substring(0, urlSep);
	this.imageAttrs = imageURL.substring(urlSep + 1).parseQueryString();
	// Set initial image parameters
	this.imageAttrs.width = this.containerSize.width;
	this.imageAttrs.height = this.containerSize.height;
	this.imageAttrs.top = (this.imageAttrs.top == undefined) ? 0.0 : this.imageAttrs.top.toFloat();
	this.imageAttrs.left = (this.imageAttrs.left == undefined) ? 0.0 : this.imageAttrs.left.toFloat();
	this.imageAttrs.bottom = (this.imageAttrs.bottom == undefined) ? 1.0 : this.imageAttrs.bottom.toFloat();
	this.imageAttrs.right = (this.imageAttrs.right == undefined) ? 1.0 : this.imageAttrs.right.toFloat();
	// Set zoom state
	this.zoomAttrs = {
		orig_width: this.imageAttrs.width,
		orig_height: this.imageAttrs.height,
		orig_top: this.imageAttrs.top,
		orig_left: this.imageAttrs.left,
		orig_bottom: this.imageAttrs.bottom,
		orig_right: this.imageAttrs.right
	};
	this.zoomAttrs.factorIn = 0.3; // 30%
	this.zoomAttrs.factorOut = 1 / (1 - this.zoomAttrs.factorIn);
	this.zoomAttrs.level = 1;
	this.zoomAttrs.levels = 10;
	// Create an image element
	this.imageEl = imageEl ? imageEl : new Element('img', {
		'oncontextmenu': 'return false',
		'ondragstart': 'return false',
		'onselectstart': 'return false'
	});
}

ImgSimpleView.prototype.init = function(refreshImage) {
	// Check we have the minimum vars to function
	if ((this.baseURL.length > 0) &&
			 this.imageAttrs.src && 
	   ((this.imageAttrs.width > 0) || (this.imageAttrs.height > 0))) {
		// Set initial view
		if (refreshImage) {
			// Remove any previous image (in case init is being called a 2nd time)
			this.containerEl.empty();
			this.containerEl.grab(this.imageEl);
			this.refresh();
		}
		// Set UI handlers
		this.imageEl.removeEvents('click');
		this.imageEl.addEvent('click', function(e) { this.onImageClick(e); }.bind(this));
	}
}

ImgSimpleView.prototype.reset = function() {
	// Return to the starting view
	this.imageAttrs.width = this.zoomAttrs.orig_width;
	this.imageAttrs.height = this.zoomAttrs.orig_height;
	this.imageAttrs.top = this.zoomAttrs.orig_top;
	this.imageAttrs.left = this.zoomAttrs.orig_left;
	this.imageAttrs.bottom = this.zoomAttrs.orig_bottom;
	this.imageAttrs.right = this.zoomAttrs.orig_right;
	this.zoomAttrs.level = 1;
	this.refresh();
}

ImgSimpleView.prototype.refresh = function() {
	if (this.zoomAttrs.level > 1) {
		// Don't cache zoomed images, the crop positions are (more or less) unique every time
		this.imageAttrs.cache = 0;
		this.imageAttrs.autocropfit = 1;
		this.imageAttrs.stats = 0;
	}
	else {
		// Fully zoomed out
		delete this.imageAttrs.cache;
		delete this.imageAttrs.autocropfit;
		delete this.imageAttrs.stats;
	}
	// Return an image format the browser can use.
	// Note jpeg rather than jpg for eRez compatibility.
	this.imageAttrs.format = 'jpeg';
	// Update our image's src
	this.imageEl.src = this.baseURL + '?' + Object.toQueryString(this.imageAttrs);
}

ImgSimpleView.prototype.onImageClick = function(e) {
	// Do not zoom if the image is smaller than the viewport
	if ((this.imageEl.width > 0) && (this.zoomAttrs.level == 1)) {
		if ((this.containerSize.width - this.imageEl.width > 2) &&
				(this.containerSize.height - this.imageEl.height > 2)) {
			this.zoomAttrs.levels = 1;
		}
	}
	
	// Zoom in (click), or out (shift-click), or just rectangle shift (alt-click)
	var zoomIn = e.alt ? null : !e.shift;
	if (zoomIn != null) {
		// Prevent zoom too far
		if ((zoomIn && this.zoomAttrs.level == this.zoomAttrs.levels) ||
		   (!zoomIn && this.zoomAttrs.level == 1)) {
			return;
		}
		// Just reset if we're going back to zoom level 1
		if (!zoomIn && this.zoomAttrs.level == 2) {
			this.reset();
			return;
		}
	}

	// Get click position inside the image
	var imagePagePos = this.imageEl.getPosition();
	var clickPos = { x: (e.page.x - imagePagePos.x), y: (e.page.y - imagePagePos.y)	};
	
	// Work out rectangle shift based on where the user clicked
	var oldCropWidth  = this.imageAttrs.right - this.imageAttrs.left;
	var oldCropHeight = this.imageAttrs.bottom - this.imageAttrs.top;
	var centreXOffset = clickPos.x - (this.containerSize.width / 2);
	var centreYOffset = clickPos.y - (this.containerSize.height / 2);
	var shiftX = (centreXOffset / this.containerSize.width) * oldCropWidth;
	var shiftY = (centreYOffset / this.containerSize.height) * oldCropHeight;

	if (zoomIn != null) {
		// Set new zoom level
		this.zoomAttrs.level += (zoomIn ? 1 : -1);
				
		// Work out the new cropping rectangle
		var cropXdiff  = zoomIn ? 
				(this.zoomAttrs.factorIn * oldCropWidth) : 
				-1.0 * ((this.zoomAttrs.factorOut * oldCropWidth) - oldCropWidth);
		var cropYdiff  = zoomIn ? 
				(this.zoomAttrs.factorIn * oldCropHeight) : 
				-1.0 * ((this.zoomAttrs.factorOut * oldCropHeight) - oldCropHeight);	

		// Set new crop rectangle (zooms from image centre)
		this.imageAttrs.top += (cropYdiff / 2);
		this.imageAttrs.left += (cropXdiff / 2);
		this.imageAttrs.bottom -= (cropYdiff / 2);
		this.imageAttrs.right -= (cropXdiff / 2);
	}
	
	// Ensure rectangle shift doesn't go outside the start cropping positions
	if (this.imageAttrs.top + shiftY < this.zoomAttrs.orig_top)    // when shiftY is negative
		shiftY = this.zoomAttrs.orig_top - this.imageAttrs.top;
	if (this.imageAttrs.left + shiftX < this.zoomAttrs.orig_left)  // when shiftX is negative
		shiftX = this.zoomAttrs.orig_left - this.imageAttrs.left;
	if (this.imageAttrs.bottom + shiftY > this.zoomAttrs.orig_bottom)
		shiftY = this.zoomAttrs.orig_bottom - this.imageAttrs.bottom;
	if (this.imageAttrs.right + shiftX > this.zoomAttrs.orig_right)
		shiftX = this.zoomAttrs.orig_right - this.imageAttrs.right;
	
	// Apply rectangle shift (move zoom to where user clicked, limit to original edges).
	// Round to handle float inexactness.
	this.imageAttrs.top = this.round(Math.max(this.imageAttrs.top + shiftY, this.zoomAttrs.orig_top), 8);
	this.imageAttrs.left = this.round(Math.max(this.imageAttrs.left + shiftX, this.zoomAttrs.orig_left), 8);
	this.imageAttrs.bottom = this.round(Math.min(this.imageAttrs.bottom + shiftY, this.zoomAttrs.orig_bottom), 8);
	this.imageAttrs.right = this.round(Math.min(this.imageAttrs.right + shiftX, this.zoomAttrs.orig_right), 8);
	
	this.refresh();
}

ImgSimpleView.prototype.round = function(num, places) {
	var rounded = Math.round(num * Math.pow(10, places)) / Math.pow(10, places);
	var rstr = ''+rounded;
	// Assume that a trailing 00x would be better off as 000
	if ((places > 2) && (rstr.length == (places + 2))) {
		if ((rstr[rstr.length - 3] == '0') && 
				(rstr[rstr.length - 2] == '0')) {
			rounded = rstr.substring(0, rstr.length - 3).toFloat();
		}
	}
	return rounded;
}

function _get_ct_viewer(ct) {
	ct = document.id(ct);
	return (ct && ct._viewer) ? ct._viewer : null;
}

/**** Public interface ****/

/* Creates and initialises an image viewer for the image with URL 'imageURL'
 * inside the element or element with ID 'container'.
 */
function simple_view_init(container, imageURL) {
	container = document.id(container);
	if (container) {
		var viewer = new ImgSimpleView(container, null, imageURL);
		viewer.init(true);
		container._viewer = viewer;
	}
	return false;
}
/* Resets the image viewer back to its original state
 */
function simple_view_reset(container) {
	var viewer = _get_ct_viewer(container);
	if (viewer) viewer.reset();
	return false;
}

/* Converts the existing image element or element with ID 'image' into a
 * zoomable image. The image must lie within a container element, in order to 
 * provide page structure when the image is replaced, and whose dimensions are
 * used as the target size for zoomed images.
 */
function simple_view_init_image(image) {
	image = document.id(image);
	if (image) {
		var viewer = new ImgSimpleView(image.getParent(), image, null);
		viewer.init(false);
		image._viewer = viewer;
	}
	return false;
}
/* Resets the image zoom back to its original state
 */
function simple_view_reset_image(image) {
	var viewer = _get_ct_viewer(image);
	if (viewer) viewer.reset();
	return false;
}
