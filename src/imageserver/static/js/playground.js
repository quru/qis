/*!
	Document:      playground.js
	Date started:  11 May 2018
	By:            Matt Fozard
	Purpose:       Quru Image Server file details helpers
	Requires:      base.js
				   common_view.js
				   canvas_view.js
	               lassocrop.js (which requires MooTools)
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
*/

"use strict";

var Playground = {
	// This is the image base URL
	imageBaseURL: '',
	// This defines the parameters for the display image
	imageSpec: {},
	imageSpecOrig: {},
	// This indicates whether selectImage() has been called at least once
	ready: false
};

// Utility - available after a resource has loaded, returns its size in bytes.
// Returns 0 on browsers that do not support the Resource Timing API, and
// intermittently on some browsers that do, when the resource comes from cache.
Playground._resourceSize = function(url) {
	if (window.performance && window.performance.getEntriesByType) {
		var resources = performance.getEntriesByType('resource');
		for (var i = 0; i < resources.length; i++) {
			if (resources[i].name === url) {
				return resources[i].decodedBodySize || 0;
			}
		}
	}
	return 0;
};

// Utility - enables a group of buttons (or other elements) to be "sticky" (like
// radio buttons) by applying the named class to the button that was clicked and
// removing it from the others. The elements require an attribute called
// "sticky-group" that must have the same value for all elements in a single
// group.  e.g. <button sticky-group="group1">Click me</button>
Playground._initStickyButtons = function(selector, activeClassName) {
	var els = document.querySelectorAll(selector);
	// Initialise loop
	for (var i = 0; i < els.length; i++) {
		els[i].addEventListener('click', function(e) {
			var clickGroup = this.getAttribute("sticky-group");
			if (clickGroup) {
				// Runtime loop - remove active class from group
				for (var j = 0; j < els.length; j++) {
					var elGroup = els[j].getAttribute("sticky-group");
					if (elGroup === clickGroup) {
						QU.elSetClass(els[j], activeClassName, false);
					}
				}
				// Set clicked item as active
				QU.elSetClass(this, activeClassName, true);
			}
		});
	}
};

// Utility - formats a bytes value
Playground._formatBytes = function(n) {
	var units = ['bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'],
		loops = 0;
	while (n >= 1024 && ++loops) {
		n /= 1024;
	}
	return(n.toFixed((n >= 10 || loops < 1) ? 0 : 1) + ' ' + units[loops]);
};

// Utility - returns the text after the first "?", or else the original text
Playground._getQS = function(url) {
	var qsIdx = url.indexOf('?');
	if (qsIdx !== -1) {
		return url.substring(qsIdx + 1);
	}
	return url;
};

// Utility - adds/removes the default "clean" image parameters
Playground._cleanImageSpec = function(spec) {
	spec.strip = false;
	delete spec.attach;
	delete spec.tmp;
	return spec;
};

// Invoked from the image selection area when a thumbnail is clicked on.
// Needs to be called once (after init()) before everything else works.
Playground.selectImage = function(imgSrc) {
	var qsIdx = imgSrc.indexOf('?');
	if (qsIdx !== -1) {
		Playground.imageBaseURL = imgSrc.substring(0, qsIdx);
		Playground.imageSpec = QU.QueryStringToObject(imgSrc.substring(qsIdx + 1), false);
		Playground.imageSpec = Playground._cleanImageSpec(Playground.imageSpec);
		Playground.imageSpecOrig = QU.clone(Playground.imageSpec);
	} else {
		Playground.imageSpec = {};
		Playground.imageSpecOrig = {};
	}
	// Hide image selection area (when present)
	var selectionEl = QU.id('pg_selection');
	if (selectionEl) {
		QU.elSetClass(selectionEl, 'selected', true);
		QU.elSetClass(QU.id('pg_main'), 'selected', true);
		setTimeout(
			Playground.onImageSelectorAnimationComplete,
			Playground.getImageSelectorAnimationDuration() + 50
		);
		// Unhide the image re-select link
		QU.elSetClass(QU.id('pg_reselect'), 'hidden', false);
	}
	// Once we have an image URL we're ready from then on
	Playground.ready = true;
	QU.elRemove('preview_image_msg');
	// Show initial preview
	Playground.reset();
};

// Shows the image selection area (when present)
Playground.openImageSelector = function() {
	var selectionEl = QU.id('pg_selection');
	if (selectionEl) {
		QU.elSetClass(selectionEl, 'selected', false);
		QU.elSetClass(QU.id('pg_main'), 'selected', false);
		setTimeout(
			Playground.onImageSelectorAnimationComplete,
			Playground.getImageSelectorAnimationDuration() + 50
		);
	}
};

// Invoked after the image selection area (when present) has been animated open or closed
Playground.onImageSelectorAnimationComplete = function() {
	if (Playground.cropTool) {
		// Lasso.Crop doesn't like animations, we need to tell it to re-measure its position
		Playground.cropTool.getRelativeOffset();
	}
};

// Returns the animation time for the image selection area, in milliseconds
Playground.getImageSelectorAnimationDuration = function() {
	var selectionEl = QU.id('pg_selection');
	if (selectionEl) {
		var styles = QU.elGetStyles(selectionEl, ['transition-duration']);
		var td = styles ? styles['transition-duration'] : '';
		if (td && td.substring(td.length - 2) == 'ms')
			return parseFloat(td);         // millis
		else if (td && td.substring(td.length - 1) == 's')
			return parseFloat(td) * 1000;  // secs
	}
	return 1000;  // Default
};

// Applies a {key: value, ...} object to Playground.imageSpec and refreshes the preview image
Playground.play = function(obj) {
	if (!Playground.ready) {
		return;
	}
	QU.merge(Playground.imageSpec, obj);
	Playground.refreshPreviewImage();
	if ((obj.angle !== undefined) || (obj.flip !== undefined)) {
		Playground.refreshCropImage();
	}
};

// Call this to show or hide the preview image file size (when available)
Playground.showPreviewImageSize = function(show) {
	var previewImg = QU.id('preview_image'),
		previewImgCtr = QU.id('preview_image_size'),
		previewImgSize = Playground._resourceSize(previewImg.src);

	if (show && previewImgSize) {
		previewImgCtr.innerText = '(file size ' + Playground._formatBytes(previewImgSize) + ')';
	} else {
		previewImgCtr.innerText = '';
	}
};

// Call this when Playground.imageSpec has changed to update the preview image
Playground.refreshPreviewImage = function() {
	if (!Playground.ready) {
		return;
	}
	var previewImg = QU.id('preview_image'),
	    waitImg = QU.id('wait_image'),
	    newSrc = Playground.imageBaseURL + '?' + QU.ObjectToQueryString(Playground.imageSpec);

	// Update image action URLs
	QU.id('view_plain').href = newSrc;
	QU.id('view_download').href = newSrc + '&amp;attach=1';
	var specCopy = QU.clone(Playground.imageSpec);
	specCopy.format = 'pdf';
	specCopy.dpi = 150;
	QU.id('view_pdf').href = Playground.imageBaseURL + '?' + QU.ObjectToQueryString(specCopy);

	// Only reload if a change has been made
	if (Playground._getQS(newSrc) !== Playground._getQS(previewImg.src)) {
		Playground.showPreviewImageSize(false);
		previewImg.src = newSrc;
		if (previewImg.complete) {
			// The image was loaded from cache, onload does not always fire so fire it manually
			Playground.onPreviewImageLoaded();
		} else {
			// The image is loading
			QU.elSetClass(previewImg, 'loading', true);
			QU.elSetClass(waitImg, 'hidden', false);
		}
	}
};

// Invoked when preview image has loaded (called either once or twice depending on browser and caching)
Playground.onPreviewImageLoaded = function() {
	if (!Playground.ready) {
		return;
	}
	var previewImg = QU.id('preview_image'),
		waitImg = QU.id('wait_image');

	QU.elSetClass(previewImg, 'loading', false);
	QU.elSetClass(previewImg, 'hidden', false);
	QU.elSetClass(waitImg, 'hidden', true);
	Playground.showPreviewImageSize(true);
};

// Call this when a change to the preview image also requires a change to the cropping image
// (for angle, flip)
Playground.refreshCropImage = function() {
	if (!Playground.ready) {
		return;
	}
	// Generate a new spec for the crop image
	var cropSpec = {
		src: Playground.imageSpec.src,
		width: 200,
		height: 200,
		autosizefit: 1,
		strip: 1,
		stats: 0
	};
	var extraProps = ['format', 'colorspace', 'angle', 'flip'];
	extraProps.forEach(function(val) {
		if (Playground.imageSpec[val]) cropSpec[val] = Playground.imageSpec[val];
	});

	var cropCtr = document.querySelector('.crop_container'),
	    cropImg = QU.id('crop_image'),
		newSrc = Playground.imageBaseURL + '?' + QU.ObjectToQueryString(cropSpec);

	// Only reload if a change has been made
	if (Playground._getQS(newSrc) !== Playground._getQS(cropImg.src)) {
		QU.elSetClass(cropCtr, 'loading', true);
		cropImg.src = newSrc;
		// If the image was in cache, onload does not always fire
		if (cropImg.complete) {
			Playground.onCropImageLoaded();
		}
	}
};

// Invoked when crop image has loaded (called either once or twice depending on browser and caching)
Playground.onCropImageLoaded = function() {
	if (!Playground.ready) {
		return;
	}
	var cropCtr = document.querySelector('.crop_container'),
	    cropImg = QU.id('crop_image');

	QU.elSetClass(cropCtr, 'loading', false);

	// Lasso.Crop doesn't support the crop image changing, so we need to re-create it every time
	if (Playground.cropTool) {
		Playground.cropTool.destroy();
	}
	Playground.cropTool = new Lasso.Crop(cropImg, {
		ratio : false,
		preset : [0, 0, cropImg.width, cropImg.height],
		min : [10, 10],
		handleSize : 10,
		opacity : 0.6,
		color : '#000',
		border : '../static/images/crop.gif',
		onComplete : Playground.onCropComplete
	});
};

// Invoked when the user has resized or moved the cropping tool
Playground.onCropComplete = function(coords) {
	var cropImg = QU.id('crop_image');
	if (!coords || (!coords.x && !coords.y && !coords.w && !coords.h)) {
		// Crop was cancelled, reset back to initial state
		Playground.cropTool.resetCoords();
		Playground.cropTool.setDefault();
		coords = Playground.cropTool.getRelativeCoords();
	}
	Playground.play({
		left: (coords.x > 0) ? (coords.x / cropImg.width) : 0,
		top: (coords.y > 0) ? (coords.y / cropImg.height) : 0,
		right: ((coords.x + coords.w) < cropImg.width) ? ((coords.x + coords.w) / cropImg.width) : 1,
		bottom: ((coords.y + coords.h) < cropImg.height) ? ((coords.y + coords.h) / cropImg.height) : 1
	});
};

// Resets/clears the cropping tool, and optionally applies the change to the preview image
Playground.resetCrop = function(apply) {
	if (Playground.cropTool) {
		Playground.cropTool.resetCoords();
		Playground.cropTool.setDefault();
		if (apply) {
			Playground.play({left: 0, top: 0, right: 1, bottom: 1});
		}
	}
};

// Launches a full screen view of the preview image using canvas_view.js
Playground.viewFullScreen = function() {
	if (!Playground.ready) {
		return;
	}
	canvas_view_init_image('preview_image');
	var viewEl = QU.id('preview_image'),
	    viewFn = viewEl._onclick;
	if (viewFn) {
		viewFn();
		viewEl.removeEventListener('click', viewFn);
	}
};

// Resets the UI controls back a standard initial state
Playground.resetUI = function() {
	// Checkboxes
	var inputs = document.querySelectorAll('.controls input');
	for (var i = 0; i < inputs.length; i++) {
		inputs[i].checked = false;
	}
	// Sticky buttons (pre-selects those with a class of default)
	var buttons = document.querySelectorAll('.controls button');
	for (var i = 0; i < buttons.length; i++) {
		QU.elSetClass(buttons[i], 'active', QU.elHasClass(buttons[i], 'default'));
	}
	// Cropping tool
	Playground.resetCrop(false);
};

// Resets everything back a standard initial state
Playground.reset = function() {
	if (!Playground.ready) {
		return;
	}
	Playground.resetUI();
	// Reset the preview image spec
	Playground.imageSpec = QU.clone(Playground.imageSpecOrig);
	QU.merge(Playground.imageSpec, {
		width: 500,
		height: 500,                     // The default sticky buttons
		format: 'jpg',                   // need to match this spec
		quality: 80,
		colorspace: 'srgb'
	});
	// Load the preview image again
	Playground.refreshPreviewImage();
	Playground.refreshCropImage();
};

// Sets up the page actions
Playground.init = function() {
	// Set up image selection
	var thumbs = document.querySelectorAll('.pg_selection img');
	for (var i = 0; i < thumbs.length; i++) {
		thumbs[i].addEventListener('click', function(e) {
			e.preventDefault();
			Playground.selectImage(this.src);
			return false;
		});
	}
	// Set up image re-selection
	var resel = document.querySelector('#pg_reselect a');
	if (resel) {
		resel.addEventListener('click', function(e) {
			e.preventDefault();
			Playground.openImageSelector();
			return false;
		});
	}
	// Set up full screen view
	QU.id('view_full').addEventListener('click', function(e) {
		e.preventDefault();
		Playground.viewFullScreen();
		return false;
	});
	// Set up preview image events
	QU.id('preview_image').addEventListener('load', Playground.onPreviewImageLoaded);
	QU.id('crop_image').addEventListener('load', Playground.onCropImageLoaded);
	// Set up sticky buttons
	Playground._initStickyButtons('.controls button', 'active');
};

QU.whenReady(Playground.init);
