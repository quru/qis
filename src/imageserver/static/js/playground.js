/*!
	Document:      playground.js
	Date started:  11 May 2018
	By:            Matt Fozard
	Purpose:       Quru Image Server file details helpers
	Requires:      base.js, common_view.js
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
	imageSpecOrig: {}
};

// Utility - returns the text after the first "?", or else the original text
Playground._getQS = function(url) {
	var qsIdx = url.indexOf('?');
	if (qsIdx !== -1) {
		return url.substring(qsIdx + 1);
	}
	return url;
};

// Invoked from the image selection area when a thumbnail is clicked on
Playground.selectImage = function(imgSrc) {
	var qsIdx = imgSrc.indexOf('?');
	if (qsIdx !== -1) {
		Playground.imageBaseURL = imgSrc.substring(0, qsIdx);
		Playground.imageSpec = QU.QueryStringToObject(imgSrc.substring(qsIdx + 1), false);
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
		// Unhide the image re-select link
		QU.elSetClass(QU.id('pg_reselect'), 'hidden', false);
	}
	// Show initial preview
	Playground.reset();
};

// Shows the image selection area (when present)
Playground.openImageSelector = function() {
	var selectionEl = QU.id('pg_selection');
	if (selectionEl) {
		QU.elSetClass(selectionEl, 'selected', false);
		QU.elSetClass(QU.id('pg_main'), 'selected', false);
	}
};

// Applies a {key: value, ...} object to Playground.imageSpec and refreshes the preview image
Playground.play = function(obj) {
	QU.merge(Playground.imageSpec, obj);
	Playground.refreshPreviewImage();
};

// Call this when Playground.imageSpec has changed to update the preview image
Playground.refreshPreviewImage = function() {
	var previewImg = QU.id('preview_image'),
	    waitImg = QU.id('wait_image'),
	    newSrc = Playground.imageBaseURL + '?' + QU.ObjectToQueryString(Playground.imageSpec);

	// Only reload if a change has been made
	if (Playground._getQS(newSrc) !== Playground._getQS(previewImg.src)) {
		QU.elSetClass(previewImg, 'loading', true);
		waitImg.style.visibility = 'visible';
		previewImg.src = newSrc;
		// If the image was in cache, onload does not always fire
		if (previewImg.complete) {
			Playground.onPreviewImageLoaded();
		}
	}
};

// Invoked when preview image has loaded (called either once or twice depending on browser and caching)
Playground.onPreviewImageLoaded = function() {
	var previewImg = QU.id('preview_image'),
	    waitImg = QU.id('wait_image');

	QU.elSetClass(previewImg, 'loading', false);
	waitImg.style.visibility = 'hidden';
};

// Resets back a standard initial state
Playground.reset = function() {
	// TODO reset UI and take w,h from there
	// Reset preview image spec
	Playground.imageSpec = QU.clone(Playground.imageSpecOrig);
	QU.merge(Playground.imageSpec, {
		width: 500,
		height: 500,
		format: 'jpg',
		colorspace: 'srgb'
	});
	// Load initial preview
	Playground.refreshPreviewImage();
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
	// Set up preview image events
	QU.id('preview_image').addEventListener('load', Playground.onPreviewImageLoaded);
};

QU.whenReady(Playground.init);
