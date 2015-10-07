/*!
	Document:      preview_popup.js
	Date started:  06 Oct 2015
	By:            Matt Fozard
	Purpose:       Quru Image Server image/iframe preview popup
	Requires:      MooTools Core 1.3 (no compat)
	               MooTools More 1.3 - Assets, String.QueryString
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
	06Oct2015  Matt  Created from bits of list.js and publish.js,
	                 converted functionality to encapsulated classes
*/

"use strict";

/*****************************************************************************/ 

// Initialises an automatic image popup for the .preview_popup element
// containerEl (as provided by inc_preview_popup.html)
function ImagePopup(containerEl) {
	this.previewState = {
		hoverEl: null,
		delayId: null,
		visible: false,
		mouseOver: false
	};
	this.previewUI = {
		containerEl: containerEl,
		waitAnimEl: containerEl.getElement('.preview_popup_waitimg'),
		imgAreaEl: containerEl.getElement('.preview_popup_right'),
		contentEl: null
	};

	// Init the preview pane
	if (containerEl.getStyle('visibility') === 'hidden') {
		containerEl.fade('hide');
	}
	containerEl.set('tween', { onComplete: this.onImagePreviewFadeComplete.bind(this) });
	containerEl.addEvent('mouseenter', this.onImagePreviewMouseIn.bind(this));
	containerEl.addEvent('mouseleave', this.onImagePreviewMouseOut.bind(this));
};

// Adds the image popup to UI elements matching a selector.
// See getPreviewImageURL() for the types of elements that are supported.
ImagePopup.prototype.attachToElements = function(selector) {
	$$(selector).each(function(el) {
		el.addEvent('mouseenter', function() { this.onElMouseIn(el); }.bind(this));
		el.addEvent('mouseleave', function() { this.onElMouseOut(el); }.bind(this));
		el.addEvent('click', function() { this.onElClick(el); }.bind(this));
	}.bind(this));
};

ImagePopup.prototype.onElMouseIn = function(el) {
	// Cancel previous popup if we've moved to a different element
	if (this.previewState.hoverEl && (this.previewState.hoverEl != el))
		this.clearImagePreview();
	// Flag popup to show after a short wait
	this.previewState.hoverEl = el;
	this.previewState.delayId = setTimeout(function() {
		this.doImagePreview();
	}.bind(this), 500);
};
ImagePopup.prototype.onElMouseOut = function(el) {
	// Bug fix - set a short delay before closing popup in case we're entering the
	// popup (mouseleave on element fires before mouseenter on the popup).
	setTimeout(function() {
		if (!this.previewState.mouseOver)
			this.clearImagePreview();
	}.bind(this), 5);
};
ImagePopup.prototype.onElClick = function(el) {
	this.clearImagePreview();
};

ImagePopup.prototype.doImagePreview = function() {
	// Flag the wait as completed
	this.previewState.delayId = null;
	
	if (this.previewState.hoverEl) {
		// Set position of the popup
		var bodyPos = $(document.body).getCoordinates();
		var previewPos = this.previewUI.containerEl.getCoordinates();
		var targetPos = this.previewState.hoverEl.getCoordinates();
		var xPos = targetPos.right + 5;

		if ((xPos + previewPos.width) > bodyPos.right)
			xPos = Math.max(targetPos.left + 30, bodyPos.right - previewPos.width);
		var yPos = (targetPos.bottom - (targetPos.height / 2)) - (previewPos.height / 2) + 1;
		this.previewUI.containerEl.setPosition({ x: xPos, y: yPos });

		// Reset the popup contents
		this.previewUI.imgAreaEl.empty();
		this.previewUI.imgAreaEl.grab(this.previewUI.waitAnimEl);
		this.previewUI.imgAreaEl.grab(new Element('span')); /* IE<8 trigger line height */
		// Request the preview image async
		this.previewUI.contentEl = Asset.image(
			this.getPreviewImageURL(this.previewState.hoverEl), {
				onLoad: function() {
					this.previewUI.imgAreaEl.empty();
					this.previewUI.imgAreaEl.grab(this.previewUI.contentEl);
					this.previewUI.imgAreaEl.grab(new Element('span')); /* IE<8 trigger line height */
				}.bind(this),
				onError: function() {
					this.previewUI.imgAreaEl.empty();
				}.bind(this)
			}
		);
		// Fade in the popup
		this.previewState.visible = true;
		this.previewUI.containerEl.fade('in');
	}
};

ImagePopup.prototype.clearImagePreview = function() {
	// Cancel the popup wait, if there is one in progress
	if (this.previewState.delayId)
		clearTimeout(this.previewState.delayId);
	// Hide the popup, if it is visible
	if (this.previewState.visible)
		this.previewUI.containerEl.fade('out');
	// Reset state
	this.previewState.hoverEl = null;
	this.previewState.delayId = null;
	this.previewState.visible = false;
	this.previewState.mouseOver = false;
};

ImagePopup.prototype.onImagePreviewMouseIn = function() {
	this.previewState.mouseOver = true;
};

ImagePopup.prototype.onImagePreviewMouseOut = function() {
	this.previewState.mouseOver = false;
	this.clearImagePreview();
};

ImagePopup.prototype.onImagePreviewFadeComplete = function() {
	// Shift popup somewhere out of the way when hidden
	if (!this.previewState.visible)
		this.previewUI.containerEl.setPosition({ x: 1, y: -1000 });
};

// Returns a preview image URL from el, where el is an anchor or inside an anchor
// that links to the details page for an image. Hmm that is quite specific!
ImagePopup.prototype.getPreviewImageURL = function(el) {
	el = $(el);
	// Find nearest anchor
	var aEl = (el.get('tag') === 'a') ? el : el.getParent('a');
	if (aEl == null) return '';
	// Use the anchor href as basis for the image URL, parse it
	var url = aEl.href.cleanQueryString().replace(/\+/g, ' ');
	var urlSep = url.indexOf('?');
	var urlBase = url.substring(0, urlSep);
	var urlAttrs = url.substring(urlSep + 1).parseQueryString();
	// Replace details URL with image URL
	urlBase = urlBase.replace('details/', 'image');
	// Set size params of our own
	urlAttrs.width = '200';
	urlAttrs.height = '200';
	urlAttrs.autosizefit = '1';
	urlAttrs.stats = '0';
	urlAttrs.strip = '1';
	urlAttrs.format = 'jpg';
	urlAttrs.colorspace = 'srgb';
	// Return the modified URL
	return urlBase + '?' + Object.toQueryString(urlAttrs);
};

/*****************************************************************************/ 

// Initialises a manual iframe popup for the .preview_popup element
// containerEl (as provided by inc_preview_popup.html)
function IframePopup(containerEl, autoclose, onclosedfn) {
	containerEl.addClass('iframe');

	this.previewUI = {
		containerEl: containerEl,
		arrowEl: containerEl.getElement('.preview_popup_left'),
		contentEl: containerEl.getElement('.preview_popup_right')
	};
	this.helpArrowHeight = this.previewUI.arrowEl.getSize().y;
	this.autoclose = autoclose;
	this.onclosed = onclosedfn;

	// Init the preview pane
	if (containerEl.getStyle('visibility') === 'hidden') {
		containerEl.fade('hide');
	}
};

// Shows the iframe preview with a url at element el
IframePopup.prototype.showAt = function(el, url) {
	// Set position of the popup
	var targetPos = $(el).getCoordinates(),
	    popupPos = this.previewUI.containerEl.getCoordinates(),
	    xPos = targetPos.right,
	    yPos = (targetPos.bottom - (targetPos.height / 2)) - (popupPos.height / 2) + 1;
	// Reset arrow position
	this.previewUI.arrowEl.setStyle('height', this.helpArrowHeight);
	// Do we need to move it down a bit?
	if (yPos < 10) {
		var yBump = 10 - yPos;
		yPos += yBump;
		this.previewUI.arrowEl.setStyle('height', this.helpArrowHeight - (yBump * 2));
	}
	// Do we need to move it up a bit?
//	if ((yPos + popupPos.height) > (yMax - 10)) {
//		var yBump = (yPos + popupPos.height) - (yMax - 10);
//		yPos -= yBump;
//		this.previewUI.arrowEl.setStyle('height', this.helpArrowHeight + (yBump * 2));
//	}
	this.previewUI.containerEl.setPosition({ x: xPos, y: yPos });
	// Reset the popup contents
	this.previewUI.contentEl.empty();
	this.previewUI.contentEl.grab(
		new Element('iframe', { src: url })
	);
	this.previewUI.containerEl.fade('in');
	// Add autoclose
	if (this.autoclose) {
		this.hideFn = this.hideFn || this.hide.bind(this);
		// Add click to close handler after this (click!) event has completed
		setTimeout(function() {
			$(document.body).addEvent('click', this.hideFn);
		}.bind(this), 1);
	}
};

IframePopup.prototype.hide = function() {
	this.previewUI.containerEl.fade('out');
	if (this.autoclose && this.hideFn) {
		$(document.body).removeEvent('click', this.hideFn);
	}
	if (this.onclosed) {
		this.onclosed();
	}
};
