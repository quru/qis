/*!
	Document:      canvas_view.js
	Date started:  22 Aug 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server HTML 5 viewer client
	Requires:      common_view.js
	               TODO delete MooTools Core 1.3 (no compat)
	               TODO delete MooTools More 1.3 - Assets, Element.Measure, Fx.Slide, Mask, Request.JSONP, String.QueryString
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
	22Sep2011  Matt  Perform zooming based on click position
	23Sep2011  Matt  Constrain panning to image area, auto-centre borders on zoom
	27Sep2011  Matt  Tweaks to add compatibility with excanvas
	10Oct2011  Matt  Added selectable animation easing functions
	12Oct2011  Matt  Re-write! Add ImgGrid class, conversion to display tiled images
	27Oct2011  Matt  Changed image/tile loading to run from a configurable queue
	02Nov2011  Matt  Added animated panning to a stop on mouse/touch release
	03Nov2011  Matt  Added loading progress bar
	15Dec2011  Matt  Added API call to get image information, pre-calculate grids
	16Jan2012  Matt  Added touch events for iOS compatibility
	24Jan2012  Matt  Added built-in UI panel with zoom controls, help
	07Feb2012  Matt  Added full-screen mode
	28Feb2012  Matt  Improved grid size choices for better zooming tile alignment
	02May2012  Matt  Changed public APIs to take options object
	03May2012  Matt  Implement destroy fns to free canvas memory on Firefox 12
	12Jun2012  Matt  Changed image info load to use JSONP transport by default
	18Sep2012  Matt  Improved touch support, add pinch to zoom
	28Feb2013  Matt  Bug fix to show control panel on top of floated page items
	03Jun2013  Matt  Set a minimum tile size
	04Jul2013  Matt  Allow the init_image methods to work with non-IMG
	                 elements that have a CSS background-image
	11Oct2013  Matt  Strip halign and valign in full-screen modes by default
	25Oct2013  Matt  Bug fix to take into account rotation before cropping,
	                 parse rotation as float not int
	11Nov2013  Matt  Add events interface and image download function
	01Apr2015  Matt  Move full-screen close button top-right to match gallery
	15Jun2015  Matt  Use standardised zoom levels + grid sizes
	14Sep2017  Matt  Remove MooTools, remove excanvas (IE8) compatibility, remove JSONP
*/

/**
 * Notes on image drawing: tiling, panning and zooming.
 *
 * The canvas context methods drawImage() and translate() will accept coordinates
 * as either integers or floats (though of course all numbers are floats in JS).
 *
 * During a zoom, we need to simultaneously pan and stretch the grid. These operations
 * must provide floats in order to achieve a smooth and straight effect. The canvas
 * correctly handles sub-pixel operations for us, anti-aliasing and drawing sub-pixel
 * boundaries very effectively.
 *
 * Outside of zooming, the grid and its tiles and the translate (pan) position
 * must all be integer aligned. If they are not, the canvas' sub-pixel handling
 * renders the image tiles in a blurry way. Also, due to float rounding errors,
 * half-pixel gaps are occasionally drawn in between the tiles.
 *
 * Care has been taken to ensure that grid and tile dimensions are always calculated
 * as integers. The code should ensure that, after zooming effects have completed,
 * the grid and translate coordinates are all restored to integer values.
 *
 * The canvas context method scale() should be avoided unless you take the above
 * into account and handle the scale factors similarly.
 */

/**
 * Notes on the image request queue.
 *
 * The need to cancel image requests arises when the user zooms in twice, quickly.
 * If several tiles were needed for display when zoom 1 completed, if they are
 * not cancelled then they will continue to load the server and stream down to us
 * even though we have since moved on to zoom 2.
 *
 * But browsers do not provide a way of cancelling image requests (deleting img.src
 * is unpredictable), so the best way to achieve this is not to request unnecessary
 * images in the first place. Hence the addition of the queue.
 *
 * The queue implemented here has 2 settings: the max number of images to download
 * simultaneously, and whether to rigidly enforce this limit. If not enforcing,
 * cancelPendingImages() allows new requests to download (up to the limit again)
 * even if there are outstanding old requests.
 *
 * The optimum settings depend on the server's level of concurrency, the image sizes,
 * server cache state, and how far and how quickly the user is likely to be zooming.
 * I ran a test, zooming in quickly 4 times on a very large (and so very slow to
 * tile) image, with an empty server cache, seeing these results to get all the
 * requested (i.e. non-cancelled) tiles downloaded:
 *   Limit 1, enforced - 51s.    Limit 1, not enforced - 2m 3s.
 *   Limit 2, enforced - 1m 24s. Limit 2, not enforced - 2m 10s.
 * Or with all relevant tiles in the server cache (and including the zooming time):
 *   Limit 1, enforced - 2.4s.   Limit 1, not enforced - 2.2s.
 *   Limit 2, enforced - 2.2s.   Limit 2, not enforced - 2.2s.
 */

/**** Mathematical helper functions ****/

Math.parseInt = function(str_val, default_ret) {
	if (!str_val || !(/^[-]*[\d]+$/.test(str_val)))
		return default_ret;
	else
		return parseInt(str_val, 10);
}
Math.parseFloat = function(str_val, default_ret) {
	if (!str_val || !(/^[-]*[.|\d]+$/.test(str_val)))
		return default_ret;
	else
		return parseFloat(str_val);
}
Math.round1 = function(num) {
	return Math.round(num * 10) / 10;
}
Math.round8 = function(num) {
	return Math.round(num * Math.pow(10, 8)) / Math.pow(10, 8);
}
Math.limit = function(num, min, max) {
	return Math.min(Math.max(num, min), max);
}
Math.roundToMultiple = function(num, mval, down) {
	var rnd = num % mval;
	if (rnd != 0) {
		if ((rnd < (mval / 2)) || down)
			rnd = -rnd;
		else
			rnd = (mval - rnd);
	}
	return Math.round(num + rnd);
}

// Easing Equations v1.5 (c) Robert Penner 2001, BSD licensed
// t: current time, b: beginning value, c: change in position, d: duration
// t and d can be in frames or seconds/milliseconds
Math.linearTween = function(t, b, c, d) {
	return c*t/d + b;
}
Math.easeOutQuad = function(t, b, c, d) {
	return -c *(t/=d)*(t-2) + b;
}
Math.easeInOutQuad = function(t, b, c, d) {
	if ((t/=d/2) < 1) return c/2*t*t + b;
	return -c/2 * ((--t)*(t-2) - 1) + b;
}
Math.easeOutSine = function(t, b, c, d) {
	return c * Math.sin(t/d * (Math.PI/2)) + b;
}
Math.easeInOutSine = function(t, b, c, d) {
	return -c/2 * (Math.cos(Math.PI*t/d) - 1) + b;
}
Math.easeOutBack = function(t, b, c, d, s) {
	if (s == undefined) s = 1.70158;
	return c*((t=t/d-1)*t*((s+1)*t + s) + 1) + b;
}
Math.easeInOutBack = function(t, b, c, d, s) {
	if (s == undefined) s = 1.70158;
	if ((t/=d/2) < 1) return c/2*(t*t*(((s*=(1.525))+1)*t - s)) + b;
	return c/2*((t-=2)*t*(((s*=(1.525))+1)*t + s) + 2) + b;
}

/**** Grid container class ****/

function ImgGrid(width, height, imageURL, stripAligns,
                 context, animationType, maxTiles, onInitialisedFn) {

	this.initialised = false;
	this.destroyed = false;
	this.onInitialisedFn = onInitialisedFn;
	this.animating = false;

	// Keep the graphics context for self-drawing
	this.g2d = {
		ctx: context,
		origin: { x: 0, y: 0 }
	};

	// Set the zoom animation type
	var animFn = Math.linearTween;
	switch (animationType.toLowerCase()) {
		case 'in-out-back':      animFn = Math.easeInOutBack; break;
		case 'in-out-quadratic': animFn = Math.easeInOutQuad; break;
		case 'in-out-sine':      animFn = Math.easeInOutSine; break;
		case 'out-back':         animFn = Math.easeOutBack; break;
		case 'out-quadratic':    animFn = Math.easeOutQuad; break;
		case 'out-sine':         animFn = Math.easeOutSine; break;
	}
	if (window.requestAnimationFrame)
	    this.animate = function(fn) { window.requestAnimationFrame(fn); };
	else
	    this.animate = function(fn) { return setTimeout(fn, 17); };

	// Track the zoom state
	this.zoom = {
		level: 1,
		nextLevel: 1,
		maxLevel: 10,
		drawZoom: { x: 1, y: 1 }, // Only while zooming, to transition between zoom levels
		animateFn: animFn
	};

	// Global grid options/properties
	this.gridOpts = {
		maxTiles:    maxTiles,
		maxWidth:    0,     // Full image size
		maxHeight:   0,
		minWidth:    0,     // Min(image size, viewport size)
		minHeight:   0,
		aspect:      1,     // Same as image aspect
		showGrid:    false  // Testing only
	};

	// Track viewport (canvas) info
	this.viewport = {
		origWidth:  width,
		origHeight: height,
		origAspect: width / height,
		width:      width,
		height:     height,
		aspect:     width / height
	};

	// Array of [zoom level]
	this.grids = new Array();
	// A shortcut to this.grids[this.zoom.level]
	this.grid = null;

	// The image request queue
	this.requests = {
		queue: new Array(),
		active: 0,             // Server requests outstanding
		limit: 	2,             // Max simultaneous server requests
		enforceLimit: true,    // See discussion above
		requested: 0,
		showProgress: false
	};

	// Parse the opening image URL
	var urlSep = imageURL.indexOf('?');
	this.urlParams = QU.QueryStringToObject(imageURL.substring(urlSep + 1), false);
	if (stripAligns) {
        delete this.urlParams.halign;
        delete this.urlParams.valign;
	}
	imageURL = imageURL.substring(0, urlSep);
	urlSep = imageURL.lastIndexOf('/');
	this.urlBase = imageURL.substring(0, urlSep + 1);
	this.urlCommand = imageURL.substring(urlSep + 1);

	// Set initial view
	this.loadingText = 'Loading image...';
	this.drawText(this.loadingText);
	this.loadImageInfo();
}

// Free up object handles
ImgGrid.prototype.destroy = function() {
	this.initialised = false;
	this.destroyed = true;
	this.cancelPendingImages();
	// Free our handle on the canvas context
	this.g2d.ctx = null;
}

// Resets the grid and view to zoom level 1
ImgGrid.prototype.reset = function() {
	if (!this.initialised || this.destroyed)
		return;

	// Stop any animation and cancel outstanding image requests
	this.animating = false;
	this.cancelPendingImages();
	// Reset pan, switch to zoom level 1 and reset the grid
	this.g2d.ctx.translate(-this.g2d.origin.x, -this.g2d.origin.y);
	this.g2d.origin.x = this.g2d.origin.y = 0;
	this.zoom.level = this.zoom.nextLevel = 1;
	this.zoom.drawZoom.x = this.zoom.drawZoom.y = 1;
	this.setGrid(1, true);
}

// Notifies the grid of a change of size of the viewport/canvas
ImgGrid.prototype.setViewportSize = function(width, height) {
	// Set new viewport size
	this.viewport.width  = width;
	this.viewport.height = height;
	this.viewport.aspect = width / height;

	// Resizing the canvas clears the current translation, so restore it
	this.g2d.ctx.translate(this.g2d.origin.x, this.g2d.origin.y);

	// Resizing the canvas clears the content, so restore it
	if (this.initialised) {
		// Re-draw the current zoom level
		this.centreGrid(true, true, false);
		this.setGrid(this.zoom.level, true);
		this.cancelPendingHiddenImages();
	}
	else if (!this.destroyed) {
		// Re-draw the loading message
		this.drawText(this.loadingText);
		// Re-centre the (invisible) grid if we have created it
		if (this.grids.length > 0) {
			this.centreGrid(true, true, false);
			this.setGrid(this.zoom.level, false);
		}
	}
}

// Loads image information
ImgGrid.prototype.loadImageInfo = function() {
	var dataURL = this.urlBase + 'api/v1/details?src=' + encodeURIComponent(this.urlParams.src);
	QU.jsonRequest(
	    dataURL,
	    'GET',
	    function(xhr, jobj) { this.onImageInfoLoaded(jobj); }.bind(this),
	    function(xhr, msg)  { this.onImageInfoFailure(xhr); }.bind(this)
	).send();
}

// Callback for image information having loaded
ImgGrid.prototype.onImageInfoLoaded = function(imgInfo) {
	if (this.destroyed)
		return;
	// Ensure the server successfully returned the image size
	if ((imgInfo.status >= 300) || (imgInfo.data.width <= 0) || (imgInfo.data.height <= 0))
		this.onImageInfoFailure(null);
	else {
		var fullWidth = imgInfo.data.width,
		    fullHeight = imgInfo.data.height;

		// FIRST If image is rotated, adjust the full width and height to reflect the angle
		if (this.urlParams.angle) {
			var absang = Math.abs(Math.parseFloat(this.urlParams.angle, 0));
			if ((absang == 90) || (absang == 270)) {
				var swap   = fullWidth;
				fullWidth  = fullHeight;
				fullHeight = swap;
			}
		}
		// SECOND If the image is cropped, adjust the full width and height to reflect the crop
		if (this.urlParams.top || this.urlParams.left || this.urlParams.right || this.urlParams.bottom) {
			var top    = Math.limit(Math.parseFloat(this.urlParams.top, 0), 0, 1),
			    left   = Math.limit(Math.parseFloat(this.urlParams.left, 0), 0, 1),
			    right  = Math.limit(Math.parseFloat(this.urlParams.right, 1), 0, 1),
			    bottom = Math.limit(Math.parseFloat(this.urlParams.bottom, 1), 0, 1);
			if ((top < bottom) && (left < right)) {
				fullWidth  = Math.round(fullWidth * (right - left));
				fullHeight = Math.round(fullHeight * (bottom - top));
			}
		}

		this.imageInfo = imgInfo.data;
		this.initialise(fullWidth, fullHeight);
	}
}

// Callback for image information load failure
ImgGrid.prototype.onImageInfoFailure = function(xhr) {
	if (!this.destroyed)
		this.drawText('X');
}

// Initialises the viewer for the given full image size
ImgGrid.prototype.initialise = function(imgwidth, imgheight) {
	// Set global grid properties
	this.gridOpts.maxWidth   = imgwidth;
	this.gridOpts.maxHeight  = imgheight;
	this.gridOpts.aspect     = imgwidth / imgheight;

	if (this.gridOpts.aspect >= this.viewport.origAspect) {
		// Fit to width
		this.gridOpts.minWidth = Math.min(imgwidth, this.viewport.origWidth);
		this.gridOpts.minHeight = Math.round(this.gridOpts.minWidth / this.gridOpts.aspect);
	}
	else {
		// Fit to height
		this.gridOpts.minHeight = Math.min(imgheight, this.viewport.origHeight);
		this.gridOpts.minWidth = Math.round(this.gridOpts.minHeight * this.gridOpts.aspect);
	}

	// Work out the available zoom levels
	for (var zl = 1; zl <= this.zoom.maxLevel; zl++) {
		// Pre-generate the grids and tile specs
		var gridSize = this.calcGridSize(zl);
		var gridSpec = this.calcGridTiles(gridSize.width, gridSize.height, gridSize.length);
		this.grids[zl] = {
			images:     [],              // Array of [tileNo] img DOM elements
			grid:       gridSpec,        // Array of [tileNo] tile definition objects
			length:     gridSize.length, // Shortcut to grid.length
			axis:       gridSize.axis,   // How many tiles per axis
			origWidth:  gridSize.width,  // Size originally, when not zooming
			origHeight: gridSize.height, // "
			width:      gridSize.width,  // Size changes when zooming, gets reset below
			height:     gridSize.height  // "
		};
		/* console.log('Grid z'+zl+' '+gridSize.width+'x'+gridSize.height+' axis '+gridSize.axis+', tiles '+gridSize.length); */

		// Check for max zoom level
		if (gridSize.max) {
			this.zoom.maxLevel = zl;
			break;
		}
	}

	// Get the initial image (sets this.initialised on image receipt)
	this.setGrid(1, false);
	this.requestImage(1, 1);
}

// Return { a, b } for the closest values of a/b = ratio, where startval is the
// starting value of a, and a and b are both multiples of mult,
// and a >= minval and a <= maxval.
ImgGrid.prototype.closestRatioMultiples = function(startval, minval, maxval, ratio, mult) {
	var a1 = Math.roundToMultiple(startval, mult),
	    b1 = Math.roundToMultiple(Math.round(a1 / ratio), mult),
	    ratio8 = Math.round8(ratio);
	// Try fast path
	if ((Math.round8(a1 / b1) == ratio8) && (a1 >= minval) && (a1 <= maxval))
		return { a: a1, b: b1 };
	else {
		// Take the slow path
		var a_from  = Math.roundToMultiple(minval, mult),
		    a_to    = Math.roundToMultiple(maxval, mult),
		    results = new Array();
		if (a_from < minval) a_from += mult;
		if (a_to > maxval) a_to -= mult;
		// Try all mults of a from a1 up to max
		for (var a2 = a1 + mult; a2 <= a_to; a2 += mult) {
			var b2 = Math.roundToMultiple(Math.round(a2 / ratio), mult), r2 = a2 / b2;
			if (Math.round8(r2) == ratio8)
				return { a: a2, b: b2 }; // 2nd fast path
			else
				results.push({ a: a2, b: b2, diff: Math.abs(ratio - r2) });
		}
		// Try all mults of a from a1 down to min
		for (var a2 = a1 - mult; a2 >= a_from; a2 -= mult) {
			var b2 = Math.roundToMultiple(Math.round(a2 / ratio), mult), r2 = a2 / b2;
			if (Math.round8(r2) == ratio8)
				return { a: a2, b: b2 }; // 2nd fast path
			else
				results.push({ a: a2, b: b2, diff: Math.abs(ratio - r2) });
		}
		// Check results
		if (results.length == 0)
			return { a: a1, b: b1 };
		else {
			// Return closest match to desired ratio
			results.sort(function(obja, objb) {
				return obja.diff - objb.diff;
			});
			return results[0];
		}
	}
}

// Returns a grid size object with the grid dimensions and number of tiles required for a given zoom level
ImgGrid.prototype.calcGridSize = function(zLevel) {
	/* This used to be dynamic based on:
	 *   factor = 1.8
	 *   multiplier = Math.pow(factor, zLevel - 1)
	 *   target width and height = nearest (tilesize * multiplier) that divides by 4/8/16.
	 *
	 * But with a fixed tilesize (v1.30.1) this evaluates to a fixed list of sizes,
	 * so now we just define that fixed list of target sizes instead.
	 *
	 * Grid size increments must be x4, anything over 256 requires increasing the
	 * default values for MAX_GRID_TILES and options.maxtiles. The dimension value
	 * must be divisible by axislen and 4 so that the fallback tiles at different
	 * zoom levels align with each other.
	 *
	 * List is [image dimension, preferred number of tiles]
	 */
	var gridSizes = [[500, 1], [960, 1], [1728, 16], [3120, 64], [5600, 64], [10240, 256],
	                 [18432, 1024], [33024, 1024], [59392, 4096], [107008, 16384]];

	if (zLevel == 1) {
		// Zoom level 1 is always the initial grid size @ 1 tile.
		var width  = this.gridOpts.minWidth,
		    height = this.gridOpts.minHeight,
		    tiles = 1,
		    axislen = 1,
		    max = (Math.max(width, height) >= gridSizes[gridSizes.length - 1][0]) ||
		          (width >= this.gridOpts.maxWidth) ||
		          (height >= this.gridOpts.maxHeight);
	}
	else {
		// Which grid size is the first one from gridOpts.min
		var useLen = (this.gridOpts.aspect >= this.viewport.origAspect) ? this.gridOpts.minWidth : this.gridOpts.minHeight,
		    gsStartIdx = 0;
		for (var i = 0; i < gridSizes.length; i++) {
			if (gridSizes[i][0] >= useLen) {
				gsStartIdx = i;
				break;
			}
		}

		// Get a rough target size, i.e. the grid size for requested zoom level
		var useIdx = Math.min(gsStartIdx + zLevel - 1, gridSizes.length - 1);
		if (this.gridOpts.aspect >= 1) {
			var width = gridSizes[useIdx][0],
			    height = Math.round(width / this.gridOpts.aspect);
		}
		else {
			var height = gridSizes[useIdx][0],
			    width = Math.round(height * this.gridOpts.aspect);
		}
		var tiles = Math.min(gridSizes[useIdx][1], this.gridOpts.maxTiles),
		    axislen = Math.round(Math.sqrt(tiles)),
		    max = (useIdx == (gridSizes.length - 1));

		// If the size is near or over the max, make it the max.
		// The server won't supply an image larger than the original, so trying to zoom
		// in further would generate, download and cache pointless identical tiles.
		// Tiling edges also fail to align when the returned image != expected size.
		if (((width / this.gridOpts.maxWidth) > 0.85) ||
		    ((height / this.gridOpts.maxHeight) > 0.85)) {
			width = this.gridOpts.maxWidth;
			height = this.gridOpts.maxHeight;
			max = true;
		}

		if (tiles > 1) {
			// Re-adjust grid size to be exactly divisible by axis size (or 4)
			// so that tile boundaries are always aligned when zooming.
			// Also try to match the image aspect ratio as closely as possible
			// to prevent tiles getting stretched during zoom animations.
			var divisor  = Math.max(axislen, 4),
			    tries    = 10,
			    minWidth = Math.max(this.gridOpts.minWidth, width - (tries * divisor)),
			    maxWidth = Math.min(this.gridOpts.maxWidth, width + (tries * divisor));

			var finalSize = this.closestRatioMultiples(
				width, minWidth, maxWidth,
				this.gridOpts.aspect,
				divisor
			);
			width  = finalSize.a;
			height = finalSize.b;
		}
	}

	return {
		width: width,
		height: height,
		length: tiles,
		axis: axislen,
		max: max
	};
}

// Returns an array of tiles and their positions for the requested grid properties.
// The returned array indexes start at 1, indexed by the tile number.
ImgGrid.prototype.calcGridTiles = function(width, height, gridLen) {
	var ret = new Array();
	if (gridLen == 1) {
		// One tile
		ret[1] = {
			tile: 1, x1: 0, y1: 0, x2: (width - 1), y2: (height - 1),
			width: width, height: height
		};
	}
	else {
		// This section is based on a port of the server code from qismagick
		var iGridAxisLen = Math.round(Math.sqrt(gridLen));
		// Get tile sizes
		var iTileWidth  = Math.floor(width / iGridAxisLen),
		    iTileHeight = Math.floor(height / iGridAxisLen),
		    iTileWidthExtra  = width % iGridAxisLen,
		    iTileHeightExtra = height % iGridAxisLen;
		// Create grid layout
		for (var i = 1; i <= gridLen; i++) {
			// Get 0-based X,Y coords for iTileNumber in the grid
			var tileXY = this.tileToXY(i, iGridAxisLen);
			// Tile position
			var tx = tileXY.x * iTileWidth,
			    ty = tileXY.y * iTileHeight;
			// Tile size (adjust for inexact division if a right/bottom tile)
			var tw = (tileXY.x == (iGridAxisLen - 1)) ? (iTileWidth + iTileWidthExtra) : iTileWidth,
			    th = (tileXY.y == (iGridAxisLen - 1)) ? (iTileHeight + iTileHeightExtra) : iTileHeight;

			ret[i] = {
				tile: i, x1: tx, y1: ty, x2: (tx + tw - 1), y2: (ty + th - 1),
				width: tw, height: th
			};
		}
	}
	return ret;
}

// Applies the grid for a given zoom level
ImgGrid.prototype.setGrid = function(zLevel, repaint) {
	// Set this.grid shortcut
	this.grid = this.grids[zLevel];
	this.grid.width = this.grid.origWidth;
	this.grid.height = this.grid.origHeight;

	// Auto-centre the grid if we should
	var fillsView = this.fillsViewport(this.grid);
	this.centreGrid(!fillsView.x, !fillsView.y, false);

	// Properly align the grid to integer boundaries
	this.alignGrid(false);

	if (repaint)
		this.paint();
}

// Returns an array of the tile numbers visible in the viewport for the current grid.
ImgGrid.prototype.getVisibleGridTiles = function() {
	var ret = new Array();
	if (this.grid.length == 1) {
		ret[0] = 1;
	}
	else {
		// Get viewport coords
		var vpx1 = -this.g2d.origin.x,
		    vpy1 = -this.g2d.origin.y,
		    vpx2 = vpx1 + this.viewport.width - 1,
		    vpy2 = vpy1 + this.viewport.height - 1;
		// See which tiles are visible in viewport
		for (var i = 1; i <= this.grid.length; i++) {
			var tileSpec = this.grid.grid[i];
			var tileOutside = ((tileSpec.x1 * this.zoom.drawZoom.x) > vpx2 ||
			                   (tileSpec.x2 * this.zoom.drawZoom.x) < vpx1 ||
			                   (tileSpec.y1 * this.zoom.drawZoom.y) > vpy2 ||
			                   (tileSpec.y2 * this.zoom.drawZoom.y) < vpy1);
			if (!tileOutside)
				ret[ret.length] = i;
		}
	}
	return ret;
}

// Converts a 1-based tile number to a 0-based x, y grid tile coordinate
ImgGrid.prototype.tileToXY = function(tileNo, gridAxis) {
	var iDiv    = Math.floor(tileNo / gridAxis),
	    iRem    = tileNo % gridAxis,
	    iTileX0 = (iRem != 0) ? (iRem - 1) : (gridAxis - 1),
	    iTileY0 = (iRem != 0) ? iDiv : (iDiv - 1);
	return { x : iTileX0, y : iTileY0 };
}

// Converts a 0-based x, y grid tile coordinate back to a 1-based tile number
ImgGrid.prototype.xyToTile = function(x, y, gridAxis) {
	return (y * gridAxis) + x + 1;
}

// Returns a fallback image and crop positions within it that will best act
// as a substitute for the given tile for the current grid.
// Note: This function requires the 1, 4, 16, (x4) grid pattern to be in effect.
//       It is called from paint so needs to be fast!
ImgGrid.prototype.getFallbackTile = function(tileNo, tileSpec) {
	var startLevel = this.zoom.level,
	    tryLevel  = startLevel;

	// Get current 0-based X,Y coords for required tile
	// and its normalised position and size
	var tileXY = this.tileToXY(tileNo, this.grid.axis),
	    rX = tileSpec.x1 / this.grid.origWidth,
	    rY = tileSpec.y1 / this.grid.origHeight,
	    rW = tileSpec.width / this.grid.origWidth,
	    rH = tileSpec.height / this.grid.origHeight;

	// Search all grids (always completes so long as this.initialised)
	while (--tryLevel >= 1) {
		var tryGrid = this.grids[tryLevel],
		    axisDiff = Math.round(this.grid.axis / tryGrid.axis),  // Note: can be 1
		    wantX = Math.floor(tileXY.x / axisDiff),
		    wantY = Math.floor(tileXY.y / axisDiff),
		    wantTileNo = this.xyToTile(wantX, wantY, tryGrid.axis),
		    donor = tryGrid.images[wantTileNo];

		if ((donor != undefined) && donor._loaded) {
			// We have a donor (the base image if tryLevel == 1).
			// Now get its normalised position and size.
			var donorSpec = tryGrid.grid[wantTileNo],
			    rDX = donorSpec.x1 / tryGrid.origWidth,
			    rDY = donorSpec.y1 / tryGrid.origHeight;
			// Return the donor and the source coords within it to achieve tileSpec
			var srcx = Math.limit(Math.round((rX - rDX) * tryGrid.origWidth), 0, donor.width - 1),
			    srcy = Math.limit(Math.round((rY - rDY) * tryGrid.origHeight), 0, donor.height - 1),
			    srcw = Math.limit(Math.round(rW * tryGrid.origWidth), 1, donor.width - srcx),
			    srch = Math.limit(Math.round(rH * tryGrid.origHeight), 1, donor.height - srcy);

			/* console.log('Fallback for z'+this.zoom.level+' tile '+tileNo+' is z'+tryLevel+' tile '+wantTileNo+' from '+srcx+','+srcy+' w'+srcw+' h'+srch); */
			return { img: donor, srcx: srcx, srcy: srcy, srcw: srcw, srch: srch };
		}
	}
}

// Returns the URL to retrieve an image or tile at a given zoom level
ImgGrid.prototype.getImageURL = function(zLevel, tileNo) {
	// Return an image format the browser can use
	this.urlParams.format = 'jpg';
	// We require exact dimensions for tile rendering to work correctly
	this.urlParams.autosizefit = '0';
	// Do not download the same old exif data with every tile
	this.urlParams.strip = '1';
	// Do not record zooms in the stats
	this.urlParams.stats = (zLevel > 1) ? '0' : '1';
	// Set required image size
	this.urlParams.width  = this.grids[zLevel].origWidth;
	this.urlParams.height = this.grids[zLevel].origHeight;
	// Set tile
	if (this.grids[zLevel].length > 1)
		this.urlParams.tile = tileNo+':'+this.grids[zLevel].length;
	else
		delete this.urlParams.tile;

	return this.urlBase + this.urlCommand + '?' + QU.ObjectToQueryString(this.urlParams);
}

// Returns the zoom level for the image to best fit the viewport.
// Always 1 unless the viewport size has changed since initialisation.
ImgGrid.prototype.getBestFitLevel = function() {
	if (!this.initialised)
		return 1;

	var levels = new Array();
	for (var i = 1; i <= this.zoom.maxLevel; i++) {
		var xdiff = Math.abs(this.viewport.width - this.grids[i].origWidth),
		    ydiff = Math.abs(this.viewport.height - this.grids[i].origHeight),
		    diff  = xdiff + ydiff;
		levels.push({ 'level': i, 'diff': diff });
	}
	levels.sort(function(obja, objb) {
		return obja.diff - objb.diff;
	});
	return levels[0].level;
}

ImgGrid.prototype.requestImage = function(zLevel, tileNo) {
	// Check this request hasn't already been serviced
	if (this.grids[zLevel].images[tileNo] != undefined)
		return;
	// Check this request isn't already queued
	for (var r, i = 0; i < this.requests.queue.length; i++) {
		r = this.requests.queue[i];
		if ((r.zLevel == zLevel) && (r.tileNo == tileNo))
			return;
	}
	// Add request to the end of the queue
	this.requests.queue.push({
		zLevel: zLevel,
		tileNo: tileNo,
		url: this.getImageURL(zLevel, tileNo),
		// Note: all callbacks need to re-poll the request queue!
		onLoad: function() {
			this.requests.active = Math.max(this.requests.active - 1, 0);
			this.onImageLoaded(zLevel, tileNo);
			this.pollImageQueue();
		}.bind(this),
		onAbort: function() {
			this.requests.active = Math.max(this.requests.active - 1, 0);
			this.pollImageQueue();
		}.bind(this),
		onError: function() {
			this.requests.active = Math.max(this.requests.active - 1, 0);
			this.pollImageQueue();
		}.bind(this)
	});
	// Update progress for the current round of requests
	this.requests.requested++;
	// Only show progress bar if the image(s) requested take a while to arrive
	// (prevent it flickering in and out when images are in the browser cache)
	if (this.requests.requested == 1) {
		setTimeout(function() {
			if (this.requests.requested > 0) {
				this.requests.showProgress = true;
				this.paint();
			}
		}.bind(this), 500);
	}
	// Load first/next in the request queue
	this.pollImageQueue();
}

// Loads the next image(s) from the request queue
ImgGrid.prototype.pollImageQueue = function() {
	while ((this.requests.queue.length > 0) &&
	       (this.requests.active < this.requests.limit)) {
		this.requests.active++;
		// Remove top request from the queue
		var req = this.requests.queue.splice(0, 1)[0];
		// Create image element to load it from the server
		var imgEl = document.createElement('img');
		imgEl.onload = req.onLoad;
		imgEl.onabort = req.onAbort;
		imgEl.onerror = req.onError;
		imgEl.src = req.url;
        this.grids[req.zLevel].images[req.tileNo] = imgEl;
	}
	// Reset progress count when nothing left
	if ((this.requests.queue.length == 0) && (this.requests.active == 0)) {
		this.requests.requested = 0;
		this.requests.showProgress = false;
		this.paint();
	}
}

// Callback for an image or tile having loaded
ImgGrid.prototype.onImageLoaded = function(zLevel, tileNo) {
	// Mark image as loaded
	var imgEl = this.grids[zLevel].images[tileNo];
	imgEl._loaded = true;

	// Set us as initialised on receipt of first image
	if (!this.initialised && (zLevel == 1)) {
		this.initialised = true;
		if (this.onInitialisedFn)
			setTimeout(function() { this.onInitialisedFn(this.imageInfo); }.bind(this), 1);
	}

	// Draw the image if we were waiting for it
	if ((zLevel == this.zoom.level) && !this.animating)
		this.paint();
}

// Cancels pending requests for tiles that are not currently visible
ImgGrid.prototype.cancelPendingHiddenImages = function() {
	var visibleTiles = this.getVisibleGridTiles();
	for (var i = 0; i < this.requests.queue.length; i++) {
		var req = this.requests.queue[i];
		if ((req.zLevel != this.zoom.level) || !visibleTiles.contains(req.tileNo)) {
			// Remove tile from requests
			this.requests.queue.splice(i, 1);
			this.requests.requested--;
			i--;
		}
	}
}

// Cancels all pending image/tile requests
ImgGrid.prototype.cancelPendingImages = function() {
	this.requests.queue.length = 0;
	// Control whether we allow the next request to load (usually the first tile at
	// a new zoom level), even if that means exceeding the request limit. If we
	// enforce the limit, the next image request must wait for anything that is
	// still outstanding.
	if (!this.requests.enforceLimit)
		this.requests.active = 0;
}

// Returns an {x, y} boolean response for whether the given object
// (with width and height attributes) can fill the viewport
// horizontally (x) and/or vertically (y).
ImgGrid.prototype.fillsViewport = function(obj) {
	return {
		x: (obj.width >= this.viewport.width),
		y: (obj.height >= this.viewport.height)
	};
}

// Shifts the graphics context in 2D space to centre the current
// grid vertically and/or horizontally, in the viewport.
// Note: changes the translate position to be fractional.
ImgGrid.prototype.centreGrid = function(horizontal, vertical, repaint) {
	var x = (this.viewport.width - this.grid.width) / 2,
	    y = (this.viewport.height - this.grid.height) / 2;
	var dx = horizontal ? (x - this.g2d.origin.x) : 0,
	    dy = vertical ? (y - this.g2d.origin.y) : 0;

	if ((dx != 0) || (dy != 0)) {
		this.g2d.ctx.translate(dx, dy);
		this.g2d.origin.x += dx;
		this.g2d.origin.y += dy;
	}

	if (repaint)
		this.paint();
}

// Shifts the graphics context in 2D space, optionally constraining movement
// vertically and/or horizontally to avoid the grid edges showing.
// Note: changes the translate position to be fractional if dx or dy is fractional.
// Returns whether any panning occurred.
ImgGrid.prototype.panGrid = function(dx, dy, constrain_h, constrain_v) {
	if (!this.initialised)
		return false;

	if (constrain_h || constrain_v) {
		if (constrain_h && (this.grid.width >= this.viewport.width)) {
			if (this.g2d.origin.x + dx > 0)
				// prevent left img edge showing
				dx = -this.g2d.origin.x;
			else if (this.g2d.origin.x + this.grid.width + dx < this.viewport.width)
				// prevent right img edge showing
				dx = -((this.grid.width - this.viewport.width) + this.g2d.origin.x);
		}
		else
			dx = 0; // width smaller than canvas, prevent panning

		if (constrain_v && (this.grid.height >= this.viewport.height)) {
			if (this.g2d.origin.y + dy > 0)
				// prevent top img edge showing
				dy = -this.g2d.origin.y;
			else if (this.g2d.origin.y + this.grid.height + dy < this.viewport.height)
				// prevent bottom img edge showing
				dy = -((this.grid.height - this.viewport.height) + this.g2d.origin.y);
		}
		else
			dy = 0; // height smaller than canvas, prevent panning
	}

	if ((dx != 0) || (dy != 0)) {
		// Pan
		this.g2d.ctx.translate(dx, dy);
		this.g2d.origin.x += dx;
		this.g2d.origin.y += dy;
		this.paint();
		return true;
	}
	return false;
}

// Animates a shift of the graphics context in 2D space
ImgGrid.prototype.autoPanGrid = function(dx, dy) {
	if (!this.initialised || this.animating)
		return;

	// Check that we can pan
	if ((this.grid.width <= this.viewport.width) &&
	    (this.grid.height <= this.viewport.height))
		return;

	// If grid should be auto-centered, only allow pan in one direction
	var fillsView = this.fillsViewport(this.grid);
	if (!fillsView.x) dx = 0;
	if (!fillsView.y) dy = 0;

	// Start animated zoom to new size
	this.animating = true;
	this.animate(function() { this.animatePan(1, 20, dx, dy, Math.easeOutQuad); }.bind(this));
}

// Shifts the graphics context in 2D space to remove any fractional alignment
ImgGrid.prototype.alignGrid = function(repaint) {
	var dx = this.g2d.origin.x - Math.round(this.g2d.origin.x),
	    dy = this.g2d.origin.y - Math.round(this.g2d.origin.y);

	if ((dx != 0) || (dy != 0)) {
		this.g2d.ctx.translate(-dx, -dy);
		this.g2d.origin.x = Math.round(this.g2d.origin.x);
		this.g2d.origin.y = Math.round(this.g2d.origin.y);
	}

	if (repaint)
		this.paint();
}

// Moves to the zoom level that best fits the image into the viewport
ImgGrid.prototype.zoomFit = function() {
	if (!this.initialised || this.animating)
		return;

	var toLevel = this.getBestFitLevel(),
	    dLevel  = toLevel - this.zoom.level;

	if (dLevel != 0)
		this.zoomGrid(dLevel, { x: 0.5, y: 0.5 });
}

// Moves to a new zoom level (+/- 1), animating the zoom towards the given point
ImgGrid.prototype.zoomGrid = function(delta, zoomCentre) {
	if (!this.initialised || this.animating)
		return;

	var newLevel = Math.limit(this.zoom.level + delta, 1, this.zoom.maxLevel);
	if (newLevel != this.zoom.level) {
		// Abandon requests for outstanding tiles
		this.cancelPendingImages();
		// Set next zoom level
		this.zoom.nextLevel = newLevel;
		var targetSize = {
			width: this.grids[newLevel].origWidth,
			height: this.grids[newLevel].origHeight
		};
		// Start animated zoom to new size
		this.animating = true;
		this.animate(function() {
			this.animateZoom(1, 20,
				this.grid.width,
				this.grid.height,
				targetSize.width - this.grid.width,
				targetSize.height - this.grid.height,
				(targetSize.width / targetSize.height) - (this.grid.width / this.grid.height),
				zoomCentre,
				this.zoom.animateFn
			);
		}.bind(this));
	}
}

// Zoom animation routine, invoked for every frame
ImgGrid.prototype.animateZoom = function(frame, frames, startWidth, startHeight,
                  changeWidth, changeHeight, changeAspect, centrePoint, easeFn) {
	// Check for reset
	if (!this.animating)
		return;

	// Get the numbers
	var prevWidth  = this.grid.width,
	    prevHeight = this.grid.height,
	    newWidth   = easeFn(frame, startWidth, changeWidth, frames),
	    newHeight  = easeFn(frame, startHeight, changeHeight, frames),
	    dw         = newWidth - prevWidth,
	    dh         = newHeight - prevHeight;

	// Set zoom vars
	this.grid.width = newWidth;
	this.grid.height = newHeight;
	this.zoom.drawZoom.x = newWidth / startWidth;
	this.zoom.drawZoom.y = newHeight / startHeight;

	// Draw zoom
	var fillsView = this.fillsViewport(this.grid);
	if (!fillsView.x && !fillsView.y) {
		// Auto-centre both axes
		this.centreGrid(true, true);
		this.paint();
	}
	else if (!fillsView.x || !fillsView.y) {
		// Use centrePoint for the axis that is wider than the canvas,
		// and auto-centre the other axis.
		var panx = fillsView.x ? -(dw * centrePoint.x) : 0,
		    pany = fillsView.y ? -(dh * centrePoint.y) : 0;
		this.centreGrid(!fillsView.x, !fillsView.y);
		if (!this.panGrid(panx, pany, fillsView.x, fillsView.y))
			this.paint();
	}
	else {
		// Use the provided centrePoint, where 0.5, 0.5 is the grid centre.
		if (!this.panGrid(-(dw * centrePoint.x), -(dh * centrePoint.y), true, true))
			this.paint();
	}

	// Continue/finish animation
	if (++frame <= frames) {
		this.animate(function() {
			this.animateZoom(frame, frames, startWidth, startHeight,
			     changeWidth, changeHeight, changeAspect, centrePoint, easeFn);
		}.bind(this));
		return;
	}
	this.onAnimateZoomComplete();
}

// Callback for the zoom animation having completed
ImgGrid.prototype.onAnimateZoomComplete = function() {
	// Flag this first so that the setGrid re-paint knows animation has finished
	this.animating = false;
	// Set new zoom level
	this.zoom.level = this.zoom.nextLevel;
	this.zoom.drawZoom.x = this.zoom.drawZoom.y = 1;
	this.setGrid(this.zoom.level, true);
	this.cancelPendingHiddenImages();
}

// Pan animation routine, invoked for every frame
ImgGrid.prototype.animatePan = function(frame, frames, dx, dy, easeFn) {
	// Check for reset
	if (!this.animating)
		return;

	var panx = easeFn(frame, 0, dx, frames),
	    pany = easeFn(frame, 0, dy, frames);

	if (this.panGrid(dx - panx, dy - pany, true, true)) {
		// Continue/finish animation
		if (++frame <= frames) {
			this.animate(function() { this.animatePan(frame, frames, dx, dy, easeFn); }.bind(this));
			return;
		}
	}
	this.onAnimatePanComplete();
}

// Callback for the pan animation having completed
ImgGrid.prototype.onAnimatePanComplete = function() {
	this.animating = false;
	this.alignGrid(true);
	this.cancelPendingHiddenImages();
}

// Renders a single line of text in the centre of the viewport
ImgGrid.prototype.drawText = function(text) {
	var fontSize = Math.min(28, (this.viewport.width / text.length) * 0.66);
	var ctx = this.g2d.ctx;
	ctx.save();
	ctx.font = fontSize + 'pt Arial';
	ctx.fillStyle = '#aaaaaa';
	ctx.textAlign = 'center';
	ctx.textBaseline = 'middle';
	this.clear();
	ctx.fillText(text, this.viewport.width / 2, this.viewport.height / 2);
	ctx.restore();
}

// Clears the current viewport
ImgGrid.prototype.clear = function() {
	if (this.g2d.ctx)
		this.g2d.ctx.clearRect(-this.g2d.origin.x, -this.g2d.origin.y, this.viewport.width, this.viewport.height);
}

// Renders all visible grid content
ImgGrid.prototype.paint = function() {
	if (!this.initialised)
		return;

	var needTiles = [], i = 0,
	    drawTiles = this.getVisibleGridTiles(),
	    fillsView = this.fillsViewport(this.grid);

	// Erase bg if it might show
	if (!fillsView.x || !fillsView.y)
		this.clear();

	// Render all visible tiles
	for (i = 0; i < drawTiles.length; i++) {
		var tileSpec = this.grid.grid[drawTiles[i]],
		    tileImg  = this.grid.images[drawTiles[i]],
		    offs = (this.zoom.drawZoom.x < 1 ? 0.5 : 0);

		if ((tileImg != undefined) && tileImg._loaded) {
			// We have the tile image
			this.g2d.ctx.drawImage(tileImg,
				tileSpec.x1 * this.zoom.drawZoom.x,
				tileSpec.y1 * this.zoom.drawZoom.y,
				tileSpec.width * this.zoom.drawZoom.x + offs,
				tileSpec.height * this.zoom.drawZoom.y + offs
			);
		}
		else {
			// No tile image. Add to request list if we're not already waiting for it.
			if (tileImg == undefined)
				needTiles[needTiles.length] = drawTiles[i];
			// Draw a temporary tile from our best base image
			tileImg = this.getFallbackTile(drawTiles[i], tileSpec);
			this.g2d.ctx.drawImage(tileImg.img,
				tileImg.srcx,
				tileImg.srcy,
				tileImg.srcw,
				tileImg.srch,
				tileSpec.x1 * this.zoom.drawZoom.x,
				tileSpec.y1 * this.zoom.drawZoom.y,
				tileSpec.width * this.zoom.drawZoom.x + offs,
				tileSpec.height * this.zoom.drawZoom.y + offs
			);
		}
	}

	// Now that grid drawing is complete, request any missing tiles.
	// But don't bother if we're on our way to a new zoom level (the animation
	// might stutter, and we might need different tiles at the new zoom level).
	if ((needTiles.length > 0) && (this.zoom.level == this.zoom.nextLevel)) {
		for (i = 0; i < needTiles.length; i++)
			this.requestImage(this.zoom.level, needTiles[i]);
	}

	// Grid test mode
	if (this.gridOpts.showGrid)
		this.paintgrid();

	// Show loading status
	if ((this.requests.requested > 0) && this.requests.showProgress)
		this.paintprogress();
}

ImgGrid.prototype.paintprogress = function() {
	var awaiting  = this.requests.queue.length + this.requests.active,
	    progress  = (this.requests.requested - awaiting) / this.requests.requested,
	    progWidth = Math.limit(this.viewport.width / 2, 100, 300),
	    progX     = ((this.viewport.width - progWidth) / 2) - this.g2d.origin.x,
	    progY     = (this.viewport.height - 15) - this.g2d.origin.y,
	    ctx       = this.g2d.ctx;
	ctx.save();
	ctx.lineWidth = 10;
	ctx.lineCap = 'round';
	// Progress bar background
	ctx.beginPath();
	ctx.moveTo(progX, progY);
	ctx.strokeStyle = 'rgba(0,0,0,0.5)';
	ctx.lineTo(progX + progWidth, progY);
	ctx.stroke();
	// Progress bar value
	if (progress > 0) {
		ctx.beginPath();
		ctx.moveTo(progX, progY);
		ctx.strokeStyle = 'rgba(255,255,255,0.7)';
		ctx.lineTo(progX + (progWidth * progress), progY);
		ctx.stroke();
	}
	ctx.restore();
}

ImgGrid.prototype.paintgrid = function() {
	var ctx = this.g2d.ctx;
	ctx.save();
	ctx.strokeStyle = '#ff0000';
	ctx.fillStyle = '#ff0000';
	ctx.font = ((this.grid.width / 10) / (this.grid.axis / 2)) + 'pt Arial';
	ctx.textAlign = 'center';
	ctx.textBaseline = 'middle';
	for (var i = 1; i <= this.grid.length; i++) {
		var tileSpec = this.grid.grid[i];
		ctx.beginPath();
		ctx.moveTo(tileSpec.x1 * this.zoom.drawZoom.x, tileSpec.y2 * this.zoom.drawZoom.y);
		ctx.lineTo(tileSpec.x2 * this.zoom.drawZoom.x, tileSpec.y2 * this.zoom.drawZoom.y);
		ctx.lineTo(tileSpec.x2 * this.zoom.drawZoom.x, tileSpec.y1 * this.zoom.drawZoom.y);
		ctx.stroke();
		ctx.fillText(
			''+i,
			(tileSpec.x1 * this.zoom.drawZoom.x) + (tileSpec.width * this.zoom.drawZoom.x / 2),
			(tileSpec.y1 * this.zoom.drawZoom.y) + (tileSpec.height * this.zoom.drawZoom.y / 2)
		);
	}
	ctx.restore();
}

/**** UI handler class ****/

function ImgCanvasView(container, imageURL, userOpts, events) {
	// Default options
	this.options = {
		title: null,
		description: null,
		showcontrols: 'auto',
		quality: true,
		animation: 'out-quadratic',
		maxtiles: 256,
		stripaligns: false,
		doubleclickreset: true,
		controls: {
			download: false,
			title: true,
			help: true,
			reset: true,
			fullscreen: true,
			zoomin: true,
			zoomout: true
		},
		// Private options
		fullScreenFixed: true,
		fullScreenCloseOnClick: true
	};
	// Apply options
	if (userOpts) {
		this.options = QU.merge(this.options, userOpts);
	}

	this.events = events; // Public events
	this._events = {};    // Private events

	// Track UI state
	this.uiAttrs = {
		alertVisible: false,
		alertEl: null,
		fullScreen: false,
		fullMaskEl: null,
		fullSwapEl: null,
		fullCloseEl: null,
		fullKeydownFn: null,
		fullResizeFn: null,
		animating: false
	};

	// Track mouse movements
	this.mouseAttrs = {
		down: false,
		dragged: false,
		downTime: 0,
		down_x: 0,
		down_y: 0,
		last_x: 0,
		last_y: 0
	};
	this.touchAttrs = {
		last1: { x: 0, y: 0 },
		last2: { x: 0, y: 0 }
	};

	// Image data (see onContentReady)
	this.imageInfo = null;

	// Get container element
	this.ctrEl = QU.id(container);
	// Clear container of placeholder or previous content
	QU.elClear(this.ctrEl);
	QU.elSetClass(this.ctrEl, 'imageviewer', true);

	// Create our canvas element
	this.canvas = document.createElement('canvas');
	this.canvas.width = 1;
	this.canvas.	height = 1;
	// Prevent canvas getting highlighted (particularly on shift-click)
	this.canvas.unselectable = 'on';
	QU.elSetStyles(this.canvas, {
	    WebkitUserSelect: 'none',
	    MozUserSelect: 'none',
	    OUserSelect: 'none',
	    msUserSelect: 'none',
	    userSelect: 'none',
	    WebkitTapHighlightColor: 'rgba(0,0,0,0)',
	    WebkitTouchCallout: 'none'
    });

    // Position and size the canvas
	this.ctrEl.appendChild(this.canvas);
	this.layout();

	// Get the canvas context and set drawing options
	this.canvasContext = this.canvas.getContext('2d');
	if (!this.options.quality) {
		this.canvas.style.msInterpolationMode = 'nearest-neighbor';
		this.canvas.style.imageRendering = '-webkit-optimize-contrast'; // 'optimizeSpeed'
		if (this.canvasContext.mozImageSmoothingEnabled !== undefined)
			this.canvasContext.mozImageSmoothingEnabled = false;
	}

	// Create the image grid which will be the canvas content
	this.content = new ImgGrid(
		this.canvas.width, this.canvas.height,
		imageURL,
		this.options.stripaligns,
		this.canvasContext,
		this.options.animation,
		this.options.maxtiles,
		function(info) { this.onContentReady(info); }.bind(this)
	);

	// Get the parsed image src for our events
	this.imageSrc = this.content.urlParams.src;
	this.imageServer = this.content.urlBase;

	// Create the control panel
	if (this.options.showcontrols != 'no')
		this.createControls();
}

// Tell browser to free up the canvas (Firefox 12 at least needs this)
ImgCanvasView.prototype.destroy = function() {
	this.events = null;
	this.content.destroy();
	this.content = null;
	this.removeEvents();
	QU.elRemove(this.canvas);
	this.canvas = null;
	this.canvasContext = null;
}

ImgCanvasView.prototype.init = function() {
	// Set UI handlers
	this.removeEvents();
	this.addEvents();
}

// Installs canvas event handlers
ImgCanvasView.prototype.addEvents = function() {
    if ('ontouchstart' in window && window.Touch) {
        this._events.touchstart  = function(e) { this.onTouchStart(e);  }.bind(this);
        this._events.touchmove   = function(e) { this.onTouchMove(e);   }.bind(this);
        this._events.touchend    = function(e) { this.onTouchEnd(e);    }.bind(this);
        this._events.touchcancel = function(e) { this.onTouchCancel(e); }.bind(this);
        this.canvas.addEventListener('touchstart',  this._events.touchstart, false);
        this.canvas.addEventListener('touchmove',   this._events.touchmove, false);
        this.canvas.addEventListener('touchend',    this._events.touchend, false);
        this.canvas.addEventListener('touchcancel', this._events.touchcancel, false);
    }
    else {
        this._events.mousedown  = function(e) { this.onMouseDown(e); }.bind(this);
        this._events.mousemove  = function(e) { this.onMouseMove(e); }.bind(this);
        this._events.mouseup    = function(e) { this.onMouseUp(e);   }.bind(this);
        this._events.mouseleave = function(e) { this.onMouseUp(e);   }.bind(this);
        this.canvas.addEventListener('mousedown',  this._events.mousedown, false);
        this.canvas.addEventListener('mousemove',  this._events.mousemove, false);
        this.canvas.addEventListener('mouseup',    this._events.mouseup, false);
        this.canvas.addEventListener('mouseleave', this._events.mouseleave, false);
    }

    // Prevent shift-click selecting and highlighting things in IE
    // (the canvas' user-select styles cover WebKit and Gecko)
    this._events.selectstart = function(e) { return false; };
    this._events.dragstart   = function(e) { return false; };
    this.canvas.addEventListener('selectstart', this._events.selectstart, false);
    this.canvas.addEventListener('dragstart',   this._events.dragstart, false);
}

// Removes the installed canvas event handlers
ImgCanvasView.prototype.removeEvents = function() {
    for (var k in this._events) {
        this.canvas.removeEventListener(k, this._events[k], false);
    }
    this._events = {};
}

// Reads the current size/position of the container element and (re)sets the canvas size
ImgCanvasView.prototype.layout = function() {
	if (!this.canvas)
		return;

	// Get container x,y and outer dimensions (incl. borders)
	this.ctrOuterPos = QU.elOuterPosition(this.ctrEl);

	// Get container usable inner dimensions (i.e. after padding)
	this.ctrInnerPos = QU.elInnerSize(this.ctrEl, false);
	// And where the inner area begins
    var ctrInnerOffsets = QU.elInnerOffsets(this.ctrEl);
    this.ctrInnerPos.offsetLeft = ctrInnerOffsets.left;
    this.ctrInnerPos.offsetTop = ctrInnerOffsets.top;

	// Apply canvas size
	this.canvas.width = this.ctrInnerPos.width;
	this.canvas.height = this.ctrInnerPos.height;
	// Notify grid (if created)
	if (this.content)
		this.content.setViewportSize(this.canvas.width, this.canvas.height);
}

ImgCanvasView.prototype.reset = function() {
	if (!this.content)
		return;
	this.content.reset();
	this.refreshZoomControls();
}

ImgCanvasView.prototype.onMouseDown = function(e) {
	if (e.button == 0) {
		if ((e.api_event == undefined) &&
			this.options.doubleclickreset &&
		    (Date.now() - this.mouseAttrs.downTime < 300)) {
			// Treat a double click/double tap as a reset
			this.reset();
		}
		else {
		    var eventPos = QU.evPosition(e);
			this.mouseAttrs.down = true;
			this.mouseAttrs.downTime = Date.now();
			this.mouseAttrs.down_x = this.mouseAttrs.last_x = eventPos.page.x;
			this.mouseAttrs.down_y = this.mouseAttrs.last_y = eventPos.page.y;
			this.mouseAttrs.dragged = false;
			QU.elSetClass(this.canvas, 'panning', true);
		}
	}
}

ImgCanvasView.prototype.onMouseMove = function(e) {
	if (this.mouseAttrs.down) {
		this.mouseAttrs.dragged = true;
		// Do not pan until we have an image and are not busy
		if (this.content && this.content.initialised && !this.content.animating) {
			// Perform the pan redraw async so that events can
			// continue and so we don't lock up slow browsers
			setTimeout(function() {
			    var eventPos = QU.evPosition(e);
				var dx = (eventPos.page.x - this.mouseAttrs.down_x);
				var dy = (eventPos.page.y - this.mouseAttrs.down_y);
				this.content.panGrid(dx, dy, true, true);
				this.mouseAttrs.last_x = this.mouseAttrs.down_x;
				this.mouseAttrs.last_y = this.mouseAttrs.down_y;
				this.mouseAttrs.down_x = eventPos.page.x;
				this.mouseAttrs.down_y = eventPos.page.y;
			}.bind(this), 1);
		}
	}
}

ImgCanvasView.prototype.onMouseUp = function(e) {
	if (this.mouseAttrs.down) {
		this.mouseAttrs.down = false;
		QU.elSetClass(this.canvas, 'panning', false);

		// Whether to close full screen mode for clicks made within the canvas but outside the image.
		// Only really makes sense when the full screen mode canvas background colour is transparent.
		if (!this.mouseAttrs.dragged && this.uiAttrs.fullScreen && this.options.fullScreenCloseOnClick) {
			var clickPos = this.getClickPosition(e, true);
			if (clickPos.x < 0 || clickPos.x > 1 || clickPos.y < 0 || clickPos.y > 1) {
			    this.toggleFullscreen();
				return;
			}
		}

		// Do not zoom until we have an image and are not busy
		if (this.content && this.content.initialised && !this.content.animating) {
			// Animate a zoom if this was just a click (the animation is async)
			if (!this.mouseAttrs.dragged) {
				var clickPos = this.getClickPosition(e, true);
				this.content.zoomGrid((e.shiftKey ? -1 : 1), clickPos);
				this.refreshZoomControls();
			}
			else {
				// Animate the current pan to a stop (the animation is async)
			    var eventPos = QU.evPosition(e);
			    var dx = (eventPos.page.x - this.mouseAttrs.last_x);
				var dy = (eventPos.page.y - this.mouseAttrs.last_y);
				if (Math.abs(dx) > 3 || Math.abs(dy) > 3)
					this.content.autoPanGrid(dx, dy);
			}
		}
	}
}

ImgCanvasView.prototype.onTouchStart = function(e) {
	e.preventDefault();
	if (e.touches.length == 1) {
		this.onMouseDown({
		    type: 'mousedown',
			pageX: e.touches[0].pageX,
			pageY: e.touches[0].pageY,
			button: 0
		});
	}
	this.touchPosReset();
}

ImgCanvasView.prototype.onTouchMove = function(e) {
	e.preventDefault();
	if (e.touches.length == 1) {
		// Pan
		this.onMouseMove({
		    type: 'mousemove',
			pageX: e.touches[0].pageX,
			pageY: e.touches[0].pageY
		});
	}
	else if (e.touches.length == 2) {
		// Prevent accidental double-clicks on 2 fingers down
		this.mouseAttrs.downTime = 0;
		// Is this an existing 2 finger movement?
		if ((this.touchAttrs.last1.x != 0) ||
		    (this.touchAttrs.last1.y != 0) ||
		    (this.touchAttrs.last2.x != 0) ||
		    (this.touchAttrs.last2.y != 0)) {
			// Get pinch zoom direction
			var prevW = Math.abs(this.touchAttrs.last1.x - this.touchAttrs.last2.x),
			    prevH = Math.abs(this.touchAttrs.last1.y - this.touchAttrs.last2.y),
			    prevDist = Math.sqrt((prevW * prevW) + (prevH * prevH)),
			    thisW = Math.abs(e.touches[0].pageX - e.touches[1].pageX),
			    thisH = Math.abs(e.touches[0].pageY - e.touches[1].pageY),
			    thisDist = Math.sqrt((thisW * thisW) + (thisH * thisH)),
			    zoomIn = (thisDist > prevDist),
			    trigger = (Math.abs(thisDist - prevDist) > 20);
			// Do a pinch zoom
			if (trigger) {
				var zEvent = {
			        type: 'mousedown',
					pageX: Math.round(this.touchAttrs.last1.x + ((this.touchAttrs.last2.x - this.touchAttrs.last1.x) / 2)),
					pageY: Math.round(this.touchAttrs.last1.y + ((this.touchAttrs.last2.y - this.touchAttrs.last1.y) / 2)),
					button: 0,
					shiftKey: !zoomIn,
					api_event: true
				};
				this.onMouseDown(zEvent);
				this.onMouseUp(zEvent);
				this.touchPosReset();
			}
		}
		else {
			// Start 2 finger tracking
			this.touchAttrs = {
				last1: { x: e.touches[0].pageX, y: e.touches[0].pageY },
				last2: { x: e.touches[1].pageX, y: e.touches[1].pageY }
			};
		}
	}
}

ImgCanvasView.prototype.onTouchEnd = function(e) {
	e.preventDefault();
	this.onMouseUp({
	    type: 'mouseup',
		pageX: e.changedTouches[0].pageX,
		pageY: e.changedTouches[0].pageY,
		shiftKey: false
	});
	this.touchPosReset();
}

ImgCanvasView.prototype.onTouchCancel = function(e) {
	this.onMouseUp({
	    type: 'mouseup',
		pageX: e.changedTouches[0].pageX,
		pageY: e.changedTouches[0].pageY,
		shiftKey: false
	});
	this.touchPosReset();
}

ImgCanvasView.prototype.touchPosReset = function() {
	this.touchAttrs = {
		last1: { x: 0, y: 0 },
		last2: { x: 0, y: 0 }
	};
}

ImgCanvasView.prototype.onContentReady = function(imageInfo) {
	if (!this.content)
		return;
	// Override image title / description
	if (this.options.title != null)
		imageInfo.title = this.options.title;
	if (this.options.description != null)
		imageInfo.description = this.options.description;
	// Set image title / description
	this.imageInfo = imageInfo;
	this.setImageTitle(imageInfo.title);
	this.enableDownload(imageInfo.download);
	this.refreshZoomControls();
	// Auto-fit if full screen mode activated before image loaded
	if (this.uiAttrs.fullScreen)
		this.autoZoomFit();
	// Fire loaded event
	if (this.events)
		ImgUtils.fireEvent(this.events.onload, this, [this.imageSrc]);
}

// Invokes a zoom in or out so that the image best fits the visible canvas
ImgCanvasView.prototype.autoZoomFit = function() {
	if (this.content && this.content.initialised) {
		this.content.zoomFit();
		this.refreshZoomControls();
	}
}

// Invokes a zoom in or out on the current centre of the visible canvas
ImgCanvasView.prototype.autoZoom = function(zoomIn) {
	var zEvent = {
	    type: 'mousedown',
		pageX: Math.round(this.ctrOuterPos.x + this.ctrInnerPos.offsetLeft + (this.canvas.width / 2)),
		pageY: Math.round(this.ctrOuterPos.y + this.ctrInnerPos.offsetTop + (this.canvas.height / 2)),
		button: 0,
		shiftKey: !zoomIn,
		api_event: true
	};
	// Correct page coords for when this.ctrOuterPos is position:fixed
	if (this.uiAttrs.fullScreen && this.options.fullScreenFixed) {
		zEvent.pageX += window.pageXOffset;
		zEvent.pageY += window.pageYOffset;
	}
	this.onMouseDown(zEvent);
	this.onMouseUp(zEvent);
}

// Strips <tag> (or all tags) from a string, retaining the text content.
ImgCanvasView.prototype.stripTags = function(str, tag) {
	tag = tag || '';
	var regex = new RegExp("<\/?" + tag + "([^>]+)?>", "gi");
	return str.replace(regex, ' ')
}

// Returns normalised values of 0 to 1 giving the visible canvas area in
// relation to the current grid. Can be negative or above 1 if there are
// background areas visible outside the grid boundaries.
ImgCanvasView.prototype.getViewportPosition = function() {
	var visleft = -this.content.g2d.origin.x,
	    vistop  = -this.content.g2d.origin.y,
	    visw    = this.canvas.width,
	    vish    = this.canvas.height;
	return {
		left: Math.round8(visleft / this.content.grid.width),
		top: Math.round8(vistop / this.content.grid.height),
		right: Math.round8((visleft + visw) / this.content.grid.width),
		bottom: Math.round8((vistop + vish) / this.content.grid.height)
	};
}

// Returns a normalised x,y value of 0 to 1 for a click position within the
// viewport, or within the current grid (if forGrid is true). The click position
// for the grid can be negative or above 1 if the click was outside the grid
// (because the grid may not fill the canvas at low zoom levels).
ImgCanvasView.prototype.getClickPosition = function(event, forGrid) {
	// Get click coords for container
    var eventPos = QU.evPosition(event);
	var relx = eventPos.page.x - this.ctrOuterPos.x;
	var rely = eventPos.page.y - this.ctrOuterPos.y;
	// Account for when this.ctrOuterPos is position:fixed
	if (this.uiAttrs.fullScreen && this.options.fullScreenFixed) {
		relx -= window.pageXOffset;
		rely -= window.pageYOffset;
	}
	// Convert to click coords within viewport (exclude container borders, padding)
	relx -= this.ctrInnerPos.offsetLeft;
	rely -= this.ctrInnerPos.offsetTop;
	// Set viewport click position
	var clickpos = {
		x: Math.round8(relx / this.canvas.width),
		y: Math.round8(rely / this.canvas.height)
	};
	if (forGrid) {
		// Convert to grid click position
		var vispos = this.getViewportPosition();
		return {
			x: Math.round8(vispos.left + ((vispos.right - vispos.left) * clickpos.x)),
			y: Math.round8(vispos.top + ((vispos.bottom - vispos.top) * clickpos.y))
		};
	}
	else {
		return clickpos;
	}
}

// Creates and returns the control panel for the image zoomer
ImgCanvasView.prototype.createControls = function() {
	// Create toggle button
    var toggler;
	if (this.options.showcontrols == 'auto') {
		toggler = document.createElement('div');
		toggler.className = 'controltoggle panelbg';
		toggler.innerHTML = '&nbsp;';
		toggler.style.position = 'relative';  /* IE 7-8 - show on top */
		toggler.addEventListener('mousedown', this.toggleControls.bind(this), false);
		this.ctrEl.appendChild(toggler);
	}

	// Create container elements for the control panel.
	// Outer panel is full-width transparent container that implements the show/hide toggle.
	var panel_outer = document.createElement('div');
	QU.elSetStyles(panel_outer, {
	    position: 'relative',
	    width: '100%',
	    lineHeight: 'normal',
	    overflow: 'hidden',    /* hides the control panel when slid up */
	    textAlign: 'center',
	    cursor: 'default'
	});
	panel_outer.addEventListener('click', function(e) {
	    // In full screen mode, pass through the click to the underlying mask
	    if (this.uiAttrs.fullScreen && this.options.fullScreenCloseOnClick)
	        this.toggleFullscreen();
	}.bind(this), false);

	// Inner panel is the centered control panel box containing the buttons etc
	var panel_inner = document.createElement('span');
	panel_inner.className = 'controlpanel panelbg' + ((this.options.showcontrols == 'auto') ? ' up' : '');
	panel_inner.addEventListener('click', function(e) {
	    // Prevent the panel_outer click firing
	    e.stopPropagation();
	}, false);
	panel_outer.appendChild(panel_inner);

	// Create and configure the control panel buttons.
	// The nbsps are required to persuade IE to draw something.

	if (this.options.controls.title) {
		var titleArea = document.createElement('span');
		titleArea.className = 'controltitle';
		titleArea.innerHTML = 'Loading...';
		panel_inner.appendChild(titleArea);
	}
	if (this.options.controls.download) {
		var btnDownload = document.createElement('span');
		btnDownload.className = 'icon download disabled';
		btnDownload.title = 'Download';
		btnDownload.innerHTML = '&nbsp;';
		btnDownload.addEventListener('mousedown', this.downloadImage.bind(this), false);
		panel_inner.appendChild(btnDownload);

		var separator = document.createElement('span');
		separator.className = 'separator';
		separator.innerHTML = '&nbsp;';
		panel_inner.appendChild(separator);
	}
	if (this.options.controls.help) {
		var btnHelp = document.createElement('span');
		btnHelp.className = 'icon help';
		btnHelp.title = 'Help';
		btnHelp.innerHTML = '&nbsp;';
		btnHelp.addEventListener('mousedown', this.toggleHelp.bind(this), false);
		panel_inner.appendChild(btnHelp);
	}
	if (this.options.controls.reset) {
		var btnReset = document.createElement('span');
		btnReset	.className = 'icon reset';
		btnReset	.title = 'Reset zoom';
		btnReset	.innerHTML = '&nbsp;';
		btnReset.addEventListener('mousedown', this.reset.bind(this), false);
		panel_inner.appendChild(btnReset);
	}
	if (this.options.controls.zoomin) {
		var btnZin = document.createElement('span');
		btnZin.className = 'icon zoomin';
		btnZin.title = 'Zoom in';
		btnZin.innerHTML = '&nbsp;';
		btnZin.addEventListener('mousedown', function() { this.autoZoom(true); }.bind(this), false);
		panel_inner.appendChild(btnZin);
	}
	if (this.options.controls.zoomout) {
		var btnZout = document.createElement('span');
		btnZout.className = 'icon zoomout';
		btnZout.title = 'Zoom out';
		btnZout.innerHTML = '&nbsp;';
		btnZout.addEventListener('mousedown', function() { this.autoZoom(false); }.bind(this), false);
		panel_inner.appendChild(btnZout);
	}
	if (this.options.controls.fullscreen) {
		var btnFull = document.createElement('span');
		btnFull.className = 'icon fulltoggle';
		btnFull.title = 'Toggle full screen mode';
		btnFull.innerHTML = '&nbsp;';
		btnFull.addEventListener('mousedown', this.toggleFullscreen.bind(this), false);
		panel_inner.appendChild(btnFull);
	}

	// Add panel to the DOM
    this.controlpanel = panel_inner;
	this.ctrEl.appendChild(panel_outer);

	// Set rollovers
	var icons = this.controlpanel.querySelectorAll('.icon');
	for (var i = 0; i < icons.length; i++) {
	    var el = icons[i];
	    el.addEventListener('mouseover', function() { QU.elSetClass(this, 'rollover', true); }.bind(el));
	    el.addEventListener('mouseout',  function() { QU.elSetClass(this, 'rollover', false); }.bind(el));
	}
}

// Clears all rollovers in the control panel
ImgCanvasView.prototype.clearRollovers = function() {
	if (this.controlpanel) {
	    var icons = this.controlpanel.querySelectorAll('.icon');
	    for (var i = 0; i < icons.length; i++) {
	        QU.elSetClass(icons[i], 'rollover', false);
	    }
	}
}

// Sets the zoom button states in the control panel.
// Assumed to be called at the start of zoom animations (hence the use of nextLevel).
ImgCanvasView.prototype.refreshZoomControls = function() {
	if (this.content && this.content.initialised && this.controlpanel) {
		var zin = this.controlpanel.querySelector('.zoomin'),
		    zout = this.controlpanel.querySelector('.zoomout'),
		    zreset = this.controlpanel.querySelector('.reset'),
		    canZoomIn = (this.content.zoom.nextLevel < this.content.zoom.maxLevel),
		    canZoomOut = (this.content.zoom.nextLevel > 1),
		    canReset = canZoomOut;

		if (zin) QU.elSetClass(zin, 'disabled', !canZoomIn);
		if (zout) QU.elSetClass(zout, 'disabled', !canZoomOut);
		if (zreset) QU.elSetClass(zreset, 'disabled', !canReset);
	}
}

// Sets whether the image download control is available
ImgCanvasView.prototype.enableDownload = function(enable) {
	if (this.controlpanel) {
		var dld = this.controlpanel.querySelector('.download');
		if (dld) {
		    QU.elSetClass(dld, 'disabled', !enable);
			dld.title = (enable ? 'Download full image' : 'Image download not permitted');
		}
	}
}

// Sets the clickable title text for the control panel, which may be truncated
ImgCanvasView.prototype.setImageTitle = function(imageTitle) {
	if (this.controlpanel) {
		var titleEl = this.controlpanel.querySelector('.controltitle');
		if (titleEl) {
			var MAX = 24,
			    useTitle = this.stripTags(imageTitle);
			if (useTitle.length > MAX) {
				var truncIdx = useTitle.indexOf(' ', MAX - 5);
				if ((truncIdx == -1) || (truncIdx > MAX)) truncIdx = useTitle.indexOf('.', MAX - 5);
				if ((truncIdx == -1) || (truncIdx > MAX)) truncIdx = useTitle.indexOf(',', MAX - 5);
				if ((truncIdx == -1) || (truncIdx > MAX)) truncIdx = useTitle.indexOf(';', MAX - 5);
				if ((truncIdx == -1) || (truncIdx > MAX)) truncIdx = useTitle.indexOf('-', MAX - 5);
				if ((truncIdx == -1) || (truncIdx > MAX)) truncIdx = useTitle.indexOf('\n', MAX - 5);
				if ((truncIdx == -1) || (truncIdx > MAX)) truncIdx = MAX;
				useTitle = useTitle.substring(0, truncIdx) + '...';
			}
			titleEl.innerHTML = useTitle;
			if (!titleEl._cv_click) {
			    titleEl._cv_click = this.toggleImageInfo.bind(this);
			    titleEl.addEventListener('click', titleEl._cv_click, false);
			}
		}
	}
}

// Shows or hides the control panel
ImgCanvasView.prototype.toggleControls = function() {
	if (this.controlpanel) {
		this.clearRollovers();
		this.refreshZoomControls();
        // Animate control panel
		var isUp = QU.elHasClass(this.controlpanel, 'up');
	    QU.elSetClass(this.controlpanel, 'up', !isUp);
	    var toggler = this.ctrEl.querySelector('.controltoggle');
	    if (toggler) {
	        QU.elSetClass(toggler, 'up', isUp);
	    }
	}
}

// Invokes a download of the full image (requires the user to have download permission)
ImgCanvasView.prototype.downloadImage = function() {
	if (this.imageInfo && this.imageInfo.download) {
		// Fire download event
		if (this.events)
			ImgUtils.fireEvent(this.events.ondownload, this, [this.imageSrc]);
		// Trigger download
		window.location.href = this.imageServer + 'original?src=' + encodeURIComponent(this.imageSrc) + '&attach=1';
	}
}

// Shows or clears a built-in alert dialog.
// Newline characters and <br> tags are allowed in the text, but for
// security reasons (text is untrusted) all other HTML tags are stripped.
ImgCanvasView.prototype.toggleAlert = function(text) {
	if (this.uiAttrs.alertVisible) {
	    QU.elRemove(this.uiAttrs.alertEl);
		this.uiAttrs.alertEl = null;
		this.uiAttrs.alertVisible = false;
	}
	else {
		// Support \r\n or \n in the text (use &#10; or &#xA; in HTML attributes)
		text = text.replace(/\r\n?/g, '\n');
		text = text.replace(/\n/g, '<br/>');

		var alertOuter = document.createElement('div');
		QU.elSetStyles(alertOuter, {
		    position: 'absolute',
		    width: '0px',
		    height: '0px',
		    zIndex: '1102' // IE7 z-index fix
		});
        this.uiAttrs.alertEl = alertOuter;

		// Putting the alert inside a positioned parent div makes the "absolute"
		// coords relative to the parent, which gives us a handy anchor point.
		var alertInner = document.createElement('div');
		alertInner.className = 'alertpanel panelbg';
		alertInner.innerHTML = this.stripTags(text, '(?!br)');
		QU.elSetStyles(alertInner, {
		    position: 'absolute',
		    zIndex: '1102',
		    lineHeight: 'normal',
		    overflow: 'auto',
		    visibility: 'hidden'
		});
		alertInner.addEventListener('mousedown', function() {
		    this.toggleAlert();  // Close alert on click
		}.bind(this), false);
		alertInner.addEventListener('touchmove', function() {
		    return false;        // Prevent pinch zoom
		}, false);

		// Add to HTML DOM
		this.uiAttrs.alertEl.appendChild(alertInner);
		this.ctrEl.insertBefore(this.uiAttrs.alertEl, this.ctrEl.firstChild);
		// Position the window now that we can get its size, and show it
		alertInner.style.left = 	Math.round((this.canvas.width - alertInner.offsetWidth) / 2) + 'px';
		alertInner.style.top = Math.max(0, Math.round((this.canvas.height - alertInner.offsetHeight) / 2)) + 'px';
		if (alertInner.offsetHeight > this.ctrInnerPos.height) {
			// Restrict vertical height to stay within our container
			var innerOffsets = QU.elInnerOffsets(alertInner),
			    vPadding  = (innerOffsets.top + innerOffsets.bottom),
			    maxHeight = Math.max(20, (this.ctrInnerPos.height - vPadding));
			alertInner.style.height = maxHeight + 'px';
		}
		alertInner.style.visibility = 'visible';
		this.uiAttrs.alertVisible = true;
	}
}

// Shows or hides the help window for the image zoomer
ImgCanvasView.prototype.toggleHelp = function() {
	var help =
		'Desktop users: &nbsp;Click to zoom in, shift-click to zoom out, ' +
		'click and hold to pan the image' +
		(this.options.doubleclickreset ? ', and double-click to reset the zoom.' : '.') +
		'<br/><br/>' +
		'Tablet users: &nbsp;Tap to zoom in, or pinch with 2 fingers to zoom in and out, ' +
		'tap and hold to pan the image' +
		(this.options.doubleclickreset ? ', and tap twice to reset the zoom.' : '.');
	this.toggleAlert(help);
}

// Shows or hides the image info window
ImgCanvasView.prototype.toggleImageInfo = function() {
	if (this.imageInfo) {
		var info = this.imageInfo.title;
		if ((this.imageInfo.title.length > 0) && (this.imageInfo.description.length > 0))
			info += '<br/><br/>';
		info += this.imageInfo.description;
	}
	else {
		var info = 'No information available';
	}
	this.toggleAlert(info);
	// Fire info shown event
	if (this.events && this.uiAttrs.alertVisible)
		ImgUtils.fireEvent(this.events.oninfo, this, [this.imageSrc]);
}

// Toggles full screen mode
ImgCanvasView.prototype.toggleFullscreen = function() {
	// Ignore double-clicks (only affects fade-out)
	if (this.uiAttrs.animating)
		return;
	// Don't toggle while zooming
	if (this.content.animating)
		return;
	// Handle help/alert being visible
	if (this.uiAttrs.alertVisible)
		this.toggleAlert();

	// Define full screen mode event handlers
	if (this.uiAttrs.fullResizeFn == null) {
		this.uiAttrs.fullKeydownFn = function(e) { this.fullscreenKeydown(e); }.bind(this);
		this.uiAttrs.fullResizeFn = function(e) { this.fullscreenResize(); }.bind(this);
	}

	// Define a fader
	if (!this.uiAttrs.fader) {
	    this.uiAttrs.fader = new Fader(this.ctrEl, 300);
	}
	
	if (this.uiAttrs.fullScreen) {
		// Fade out container
		this.uiAttrs.animating = true;
		this.uiAttrs.fader.fadeOut(function() {
			// Remove event handlers
			window.removeEventListener('resize', this.uiAttrs.fullResizeFn, false);
			window.removeEventListener('keydown', this.uiAttrs.fullKeydownFn, false);
			// Remove the close button
			this.uiAttrs.fullCloseEl.removeEventListener('click', this.uiAttrs.fullCloseEl._onclick, false);
			QU.elRemove(this.uiAttrs.fullCloseEl);
			this.uiAttrs.fullCloseEl = null;
			// Take container back out of the page
			QU.elRemove(this.ctrEl);
			// Restore previous container styles
			QU.elSetStyles(this.ctrEl, this.uiAttrs.containerStyles);
			QU.elSetClass(this.ctrEl, 'fullscreen', false);
			// Swap back the temporary container for the real one
			this.uiAttrs.fullSwapEl.parentNode.replaceChild(this.ctrEl, this.uiAttrs.fullSwapEl);
			this.uiAttrs.fullSwapEl = null;
			// Unmask the page
			this.uiAttrs.fullMaskEl.destroy();
			this.uiAttrs.fullMaskEl = null;
			// Reset container size/location
			this.layout();
			this.clearRollovers();
			// Auto zoom out
			this.reset();

			this.uiAttrs.animating = false;
			this.uiAttrs.fullScreen = false;

			// Fire fullscreen event
			if (this.events)
				ImgUtils.fireEvent(this.events.onfullscreen, this, [this.imageSrc, false]);
		}.bind(this));
	}
	else {
		// Get container destination coords
		var fsCoords = this.fullscreenGetCoords();
		// Back up the container's styles
		this.uiAttrs.containerStyles = QU.elGetStyles(this.ctrEl,
		    ['position', 'zIndex', 'opacity', 'left', 'top', 'width', 'height', 'margin']
		);
		// Mask the page
		this.uiAttrs.fullMaskEl = new PageMask(
		    'fullscreen_mask',
		    { 'zIndex': '1100' },
		    function(mask) { this.toggleFullscreen(); }.bind(this)
		);
		this.uiAttrs.fullMaskEl.show();
		// Swap the container for a temporary placeholder of the same size
		this.uiAttrs.fullSwapEl = this.ctrEl.cloneNode(false);
		this.ctrEl.parentNode.replaceChild(this.uiAttrs.fullSwapEl, this.ctrEl);
		// Override container styles and put it back in the page, now on top of the mask
		QU.elSetStyles(this.ctrEl, {
			position: this.options.fullScreenFixed ? 'fixed' : 'absolute',
			zIndex: '1101',
			opacity: '0',
			left: fsCoords.left + 'px',
			top: fsCoords.top + 'px',
			width: fsCoords.width + 'px',
			height: fsCoords.height + 'px',
			margin: '0'
		});
		QU.elSetClass(this.ctrEl, 'fullscreen', true);
		document.body.insertBefore(this.ctrEl, document.body.firstChild);
		// Reset container size/location
		this.layout();
		this.clearRollovers();
		// Add a close button
		this.uiAttrs.fullCloseEl = document.createElement('a');
		this.uiAttrs.fullCloseEl.className = 'close_button';
		QU.elSetStyles(this.uiAttrs.fullCloseEl, {
		    display: 'block',
		    position: 'absolute',
		    zIndex: '1102',       // same as alert panel
		    top: '0px',
		    right: '0px',
		    width: '33px',
		    height: '32px'
        });
		this.uiAttrs.fullCloseEl._onclick = this.toggleFullscreen.bind(this);
		this.uiAttrs.fullCloseEl.addEventListener('click', this.uiAttrs.fullCloseEl._onclick, false);
		this.ctrEl.insertBefore(this.uiAttrs.fullCloseEl, this.ctrEl.firstChild);
		// Add event handlers
		window.addEventListener('keydown', this.uiAttrs.fullKeydownFn, false);
		window.addEventListener('resize', this.uiAttrs.fullResizeFn, false);
		// Fade in container
		this.uiAttrs.fader.fadeIn(this.autoZoomFit.bind(this)); // Auto-fit after fade in (see also onContentReady)
		this.uiAttrs.fullScreen = true;

		// Fire fullscreen event
		if (this.events)
			ImgUtils.fireEvent(this.events.onfullscreen, this, [this.imageSrc, true]);
	}
}

// Full-screen mode size and position calculation
ImgCanvasView.prototype.fullscreenGetCoords = function() {
	// Get browser total viewport size
	// #517 Prefer window.inner* to get the visual viewport in mobile browsers
	//      http://www.quirksmode.org/mobile/viewports2.html "Measuring the visual viewport"
	var winSize   = window.innerWidth ? { x: window.innerWidth, y: window.innerHeight } : { x: document.body.clientWidth, y: document.body.clientHeight },
	    winScroll = this.options.fullScreenFixed ? { x: 0, y: 0 } : { x: window.pageXOffset, y: window.pageYOffset },
	    winMargin = Math.min(Math.round(winSize.x / 40), Math.round(winSize.y / 40));
	// Get target placement of viewer container element
	var tgtLeft   = (winScroll.x + winMargin),
	    tgtTop    = (winScroll.y + winMargin),
	    tgtWidth  = (winSize.x - ((2 * winMargin) + (this.ctrOuterPos.width - this.ctrInnerPos.width))),
	    tgtHeight = (winSize.y - ((2 * winMargin) + (this.ctrOuterPos.height - this.ctrInnerPos.height)));
	// Leave room in bottom margin for the control panel
	if (this.controlpanel) {
		if (winMargin < this.controlpanel.offsetHeight)
			tgtHeight -= (this.controlpanel.offsetHeight - winMargin);
	}
	return {
		left: tgtLeft,
		top: tgtTop,
		// Enforce some minimum size
		width: Math.max(tgtWidth, 100),
		height: Math.max(tgtHeight, 100)
	};
}

// Full-screen mode keydown event handler
ImgCanvasView.prototype.fullscreenKeydown = function(e) {
    var code = (e.which || e.keyCode);
	if (code === 27) {
		// Close async because we don't want to be in here when this handler gets removed
		setTimeout(this.toggleFullscreen.bind(this), 1);
	}
}

// Full-screen mode window resize event handler
ImgCanvasView.prototype.fullscreenResize = function() {
	// The mask resizes itself.
	// We must resize the viewer container.
	var fsCoords = this.fullscreenGetCoords();
	this.ctrEl.style.left = fsCoords.left + 'px';
	this.ctrEl.style.top = fsCoords.top + 'px';
	this.ctrEl.style.width = fsCoords.width + 'px';
	this.ctrEl.style.height = fsCoords.height + 'px';
	this.layout();
}

/**** Element fader utility ****/

// Creates a fader for an element, with a fade duration in milliseconds.
// This is the IE9 version. In IE10+ you can toggle a CSS class containing a
// CSS transition, and hook into the 'transitionend' event.
function Fader(el, duration) {
    this.element = el;
    this.steps = Math.round(Math.max(1, duration / 16.66));  // 16.66 == 60fps
    this.increment = 1 / this.steps;                         // Since opacity goes from 0 to 1
    this.stepFn = this._step.bind(this);
    if (window.requestAnimationFrame)
        this.animate = function(fn) { window.requestAnimationFrame(fn); };
    else
        this.animate = function(fn) { return setTimeout(fn, 17); };
}

Fader.prototype.fadeIn = function(onCompleteFn) {
    this.onCompleteFn = onCompleteFn;
    this.step = 0;
    this.opacity = 0;
    this.direction = 1;
    this.animate(this.stepFn);
}

Fader.prototype.fadeOut = function(onCompleteFn) {
    this.onCompleteFn = onCompleteFn;
    this.step = 0;    
    this.opacity = 1;
    this.direction = -1;
    this.animate(this.stepFn);
}

Fader.prototype.destroy = function() {
    this.element = null;
    this.stepFn = function(){};
}

Fader.prototype._step = function() {
    this.opacity += (this.increment * this.direction);
    this.element.style.opacity = this.opacity;
    this.step++;
    if (this.step < this.steps) {
        this.animate(this.stepFn);
    } else if (this.onCompleteFn) {
        this.onCompleteFn();
    }
}

/**** Page mask utility ****/

// Creates an initially hidden full-page mask over the current page.
// e.g. var pm = new PageMask('mask', {'zIndex': '1', 'marginLeft': '2em'}, function(mask) { mask.hide(); });
// All parameters are optional.
function PageMask(className, styles, onClickFn) {
    this.element = document.createElement('div');
    // Add default styles before user styles
    this.element.style.position = 'fixed';
    this.element.style.left = '0px';
    this.element.style.top = '0px';
    this.element.style.width = '100vw';
    this.element.style.height = '100vh';

    if (className) {
        this.element.className = className;        
    }
    if (styles) {
        for (var key in styles) {
            this.element.style[key] = styles[key];
        }
    }
    if (onClickFn) {
        this._onclick = function(e) { onClickFn(this); }.bind(this);
        this.element.addEventListener('click', this._onclick, false);
    }
    if (!className && !styles) {
        this.element.style.backgroundColor = '#000000';
        this.element.style.opacity = '0.8';        
    }

    this.element.style.display = 'none';
    if (document.body.firstChild)
        document.body.insertBefore(this.element, document.body.firstChild);
    else
        document.body.appendChild(this.element);
}

// Shows the mask
PageMask.prototype.show = function() {
    this.element.style.display = 'block';
}

// Hides the mask but keeps it in the page
PageMask.prototype.hide = function() {
    this.element.style.display = 'none';
}

// Removes the mask from the page
PageMask.prototype.destroy = function() {
    this.hide();
    if (this._onclick) {
        this.element.removeEventListener('click', this._onclick, false);
    }
    this.element.parentNode.removeChild(this.element);
}

/**** Local utility functions ****/

ImgUtils = {};

// Asynchronously invokes a user-supplied callback function
ImgUtils.fireEvent = function (fn, thisArg, argList) {
	if (fn && typeof fn === 'function') {
		setTimeout(function() {
			fn.apply(this, argList);
		}.bind(thisArg), 1);
	}
}

// Returns the image URL of an element (img.src or css background image), or null
ImgUtils.getImageSrc = function(el) {
	// Prefer img src
	if (el.src)
		return el.src;
	// Try for a CSS background image
	var bgimg = el.style.backgroundImage;
	// Handle url(...), url('...'), or url("...")
	if (bgimg && (bgimg.length > 5) && (bgimg.indexOf('url(') === 0)) {
		bgimg = bgimg.substring(4);
		if ((bgimg.charAt(0) == '\'') || (bgimg.charAt(0) == '"'))
			return bgimg.substring(1, bgimg.length - 2);
		else
			return bgimg.substring(0, bgimg.length - 1);
	}
	return null;
}

/**** Private heleper functions ****/

function _img_fs_zoom_click(imgEl, options, events) {
	// Get image src or element background image
	var imageURL = ImgUtils.getImageSrc(imgEl);
	if (!imageURL)
		return;

	// Create a hidden div to house the ImgCanvasView
	var hiddenEl = QU.id('_cv_fs_zoom_click_el');
	if (!hiddenEl) {
		// We require a fixed width/height div here, so that the images and tiles are
		// requested at a standard size (independent of browser size), in turn so that
		// the server can cache everything properly.
		hiddenEl = document.createElement('div');
		hiddenEl.id = '_cv_fs_zoom_click_el';
		QU.elSetStyles(hiddenEl, {
		    position: 'absolute',
		    display: 'block',
		    width: '500px',
		    height: '500px',
		    left: '-1000px'
		});
		document.body.insertBefore(hiddenEl, document.body.firstChild);
	}
	// Init the hidden div
	canvas_view_init(hiddenEl, imageURL, options, events);
	// Invoke full screen mode
	canvas_view_toggle_fullscreen(hiddenEl);
}

function _get_ct_viewer(ct) {
	ct = QU.id(ct);
	return (ct && ct._cv_viewer) ? ct._cv_viewer : null;
}

/**** Public interface ****/

/* Returns whether the browser supports the canvas element
 */
function haveCanvasSupport() {
	if (window._hcvs === undefined) {
		var cvEl = document.createElement('canvas');
		window._hcvs = !!(cvEl && cvEl.getContext);
	}
	return window._hcvs;
}

/* Creates and initialises a zoomable viewer for the image with
 * URL 'imageURL' inside the element or element with ID 'container'.
 * The 'options' parameter is optional, and all options within it are also optional.
 * The 'events' parameter is optional, and all event callbacks are also optional.
 *
 * Available options:
 *
 * title - Overrides the image title in the control panel. Defaults to the image's assigned title.
 * description - Overrides the image description. Defaults to the image's assigned description.
 * showcontrols - Whether the control panel is displayed. One value from: 'yes', 'no', 'auto'.
 *                Default 'auto'.
 * quality - A boolean determining whether images are smoothed or not during zooming. Default true.
 * animation - The type of zoom animation. One value from: 'linear', 'in-out-back', 'in-out-quadratic',
 *             'in-out-sine', 'out-back', 'out-quadratic', 'out-sine'. Default 'out-quadratic'.
 * maxtiles - The maximum number of tiles to create when zooming in, or 1 to disable tiling (at maximum
 *            zoom the full image will be downloaded). Must be: 1, 4, 16, 64, or 256. Default 256.
 * controls - An inner object describing which items to display on the control panel.
 *            One or more of the following properties may be specified as a boolean:
 *            title, download, help, reset, fullscreen, zoomin, zoomout.
 *            All default to true except for download. See the examples below.
 * doubleclickreset - A boolean specifying whether to reset the zoom on double tap/click.
 *                    Default true.
 *
 * E.g. { showcontrols: 'yes', quality: true, animation: 'in-out-back' }
 * E.g. { showcontrols: 'auto', controls: { help: false, reset: false } }
 *
 * Available events:
 *
 * onload       - function(src) - fires when the initial image is displayed
 * oninfo       - function(src) - fires when the user views the image description
 * ondownload   - function(src) - fires when the full image download is invoked
 * onfullscreen - function(src, boolean) - fires when the view enters (boolean true)
 *                                            or leaves (boolean false) full-screen mode
 *
 * E.g. {
 *        onload: function(src) {
 *          alert('Image ' + src + ' is now loaded');
 *        },
 *        onfullscreen: function(src, fullscreen) {
 *          alert('Image ' + src + ' is ' + (fullscreen ? 'entering' : 'leaving') +
 *                ' full-screen mode');
 *        }
 *      }
 */
function canvas_view_init(container, imageURL, options, events) {
	container = QU.id(container);
	if (container) {
		if (haveCanvasSupport() && QU.supported) {
			// Destroy previous viewer instance (Firefox 12 at least needs this)
			if (container._cv_viewer != undefined)
				container._cv_viewer.destroy();
			// Assign new viewer instance
			var viewer = new ImgCanvasView(container, imageURL, options, events);
			viewer.init();
			container._cv_viewer = viewer;
		}
		else {
			container.innerHTML = 'Sorry, this control is unsupported. Try upgrading your web browser.';
		}
	}
	return false;
}
/* Zooms in the image viewer
 */
function canvas_view_zoom_in(container) {
	var viewer = _get_ct_viewer(container);
	if (viewer) viewer.autoZoom(true);
	return false;
}
/* Zooms out the image viewer
 */
function canvas_view_zoom_out(container) {
	var viewer = _get_ct_viewer(container);
	if (viewer) viewer.autoZoom(false);
	return false;
}
/* Toggles the image viewer's help window
 */
function canvas_view_toggle_help(container) {
	var viewer = _get_ct_viewer(container);
	if (viewer) viewer.toggleHelp();
	return false;
}
/* Toggles the image viewer's image info window
 */
function canvas_view_toggle_image_info(container) {
	var viewer = _get_ct_viewer(container);
	if (viewer) viewer.toggleImageInfo();
	return false;
}
/* Toggles the image viewer's full screen mode
 */
function canvas_view_toggle_fullscreen(container) {
	var viewer = _get_ct_viewer(container);
	if (viewer) viewer.toggleFullscreen();
	return false;
}
/* Resets the image viewer back to its original state
 */
function canvas_view_reset(container) {
	var viewer = _get_ct_viewer(container);
	if (viewer) viewer.reset();
	return false;
}
/* Notifies the image viewer that its container has been resized
 */
function canvas_view_resize(container) {
	var viewer = _get_ct_viewer(container);
	if (viewer) viewer.layout();
	return false;
}

/* Converts the existing element with ID 'image'
 * to provide a full screen zoomable image on click.
 * The 'options' and 'events' parameters are optional, see canvas_view_init for info.
 */
function canvas_view_init_image(image, options, events) {
	image = QU.id(image);
	if (image) {
		// Modify a copy of the supplied options!
		var opts = options ? QU.clone(options) : {};
		// Use img title/alt if no title specified
		var imageText = image.title || image.alt;
		if (imageText) {
			if (opts.title == undefined)
				opts.title = imageText;
		}
		// Do not keep aligned fill by default
		if (opts.stripaligns === undefined) {
			opts.stripaligns = true;
		}
		// Set onclick
		image._cv_click = function() { _img_fs_zoom_click(image, opts, events); };
		image.removeEventListener('click', image._cv_click, false);
		image.addEventListener('click', image._cv_click, false);
	}
	return false;
}

/* Converts all existing elements having class 'className'
 * to provide a full screen zoomable image on click.
 * The 'options' and 'events' parameters are optional, see canvas_view_init for info.
 */
function canvas_view_init_all_images(className, options, events) {
    var images = document.querySelectorAll('.' + className);
    for (var i = 0; i < images.length; i++) {
        canvas_view_init_image(images[i], options, events);
    }
	return false;
}
