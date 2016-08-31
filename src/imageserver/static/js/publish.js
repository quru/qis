/*!
	Document:      publish.js
	Date started:  29 Oct 2014
	By:            Matt Fozard
	Purpose:       Quru Image Server image publish wizard
	Requires:      base.js
	               preview_popup.js
	               MooTools More 1.3 - String.QueryString
	               highlight.js
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
	06Oct2015  Matt  Refactored help popup JS into preview_popup.js
	12Oct2015  Matt  Added HTML5 <picture> and <img srcset> outputs
	31Aug2016  Matt  v2.2 Replaced server defaults with default template
*/

"use strict";

var Publisher = {
	// Track preview image requests so we don't accidentally hammer the server
	// (e.g. by leaning on the rotation angle increment button)
	previewImageRC: 0,
	cropImageRC: 0,
	// This contains a copy of the base template
	templateSpec: {},
	// This defines the parameters for the final image
	imageSpec: {},
	// The preview image uses these too but overrides some (e.g. width and height)
	previewSpec: {}
};

Publisher.init = function() {
	// Add UI event handlers
	addEventEx('crop_image', 'load', Publisher.refreshedCropImage);
	addEventEx('crop_image', 'load', Publisher.initCropping);
	addEventEx('preview_image', 'load', function() { Publisher.refreshedPreview(false); });
	addEventEx('preview_image', 'error', function() { Publisher.refreshedPreview(true); });
	addEventEx('publish_field_template', 'change', Publisher.onTemplateChanged);
	addEventEx('publish_field_page', 'change', Publisher.onPageChanged);
	addEventEx('publish_field_fill', 'change', Publisher.onFillChanged);
	addEventEx('publish_field_autofill', 'change', Publisher.onAutoFillChanged);
	addEventEx('publish_field_transfill', 'change', Publisher.onTransFillChanged);
	addEventEx('publish_field_flip', 'change', Publisher.onFlipChanged);
	addEventEx('publish_field_rotation', 'change', Publisher.onRotationChanged);
	addEventEx('sizing_units', 'change', Publisher.onUnitsChanged);
	addEventEx('overlay_src_browse', 'click', Publisher.onBrowseOverlay);
	addEventEx('publish_download', 'click', Publisher.onPublishDownload);
	addEventEx('publish_type', 'change', Publisher.onPublishTypeChanged);
	$$('img.help').each(function(img) {
		addEventEx(img, 'click', function() { Publisher.toggleHelp(img); });
	});
	$$('.publish_field').each(function(el) {
		addEventEx(el, 'change', Publisher.onChange);
	});
	// Popup help (see preview_popup.js)
	Publisher.popupHelp = new IframePopup(
		$$('.preview_popup')[0], true, function() {
			Publisher.showingHelp = false;
		}
	);
	// Browser feature detection
	Publisher.hasOuterHTML = ($('publish_output').outerHTML !== undefined);
	// Set initial state
	Publisher.initSpecs();
	Publisher.onTemplateChanged();
	Publisher.onUnitsChanged(null, true);
	Publisher.refreshPublishOutput();
	// IE doesn't fire onload if the image was cached and displayed already
	if ($('crop_image').complete) {
		Publisher.initCropping();
	}
};

Publisher.initSpecs = function() {
	var imgSrc = $('preview_image').getProperty('src'),
	    urlSep = imgSrc.indexOf('?'),
	    imgParams = imgSrc.substring(urlSep + 1).cleanQueryString().replace(/\+/g, ' ');

	// Default the preview image spec (size, format) from the HTML <img>
	Publisher.previewURL = imgSrc.substring(0, urlSep);
	Publisher.previewSpec = imgParams.parseQueryString();
	// We don't want to cache all the generated previews
	Publisher.previewSpec.cache = '0';
	Publisher.previewSpec.stats = '0';

	// Only default the src for the final image spec
	Publisher.imageURL = PublisherConfig.external_image_url;
	Publisher.imageSpec.src = Publisher.previewSpec.src;
};

Publisher.onBrowseOverlay = function() {
	popup_iframe($(this).getProperty('data-browse-url'), 575, 650);
	return false;
};

Publisher.onTemplateChanged = function() {
	var infoEl = $('template_fields'),
	    tempEl = $('publish_field_template'),
	    tempVal = tempEl.options[tempEl.selectedIndex].getProperty('data-id'),
	    apiURL = PublisherConfig.template_api_url;

	Publisher.templateSpec = {};
	infoEl.empty();
	infoEl.set('text', PublisherText.loading);

	if (!tempVal) {
		tempVal = PublisherConfig.default_template_id;
	}
	new Request.JSON({
		url: apiURL.replace('/0/', '/' + tempVal + '/'),
		onSuccess: function(jsonObj, jsonText) {
			Publisher.setTemplateInfo(infoEl, jsonObj.data);
		},
		onFailure: function(xhr) {
			infoEl.set('text', PublisherText.loading_failed);
		}
	}).get();
};

Publisher.onUnitsChanged = function(e, init) {
	var dpiEl = $('publish_field_dpi_x'),
	    widthEl = $('publish_field_width'),
	    heightEl = $('publish_field_height'),
	    unitsEl = $('sizing_units'),
	    units = unitsEl.options[unitsEl.selectedIndex].value,
	    dpi = parseInt(dpiEl.value, 10) || PublisherConfig.default_print_dpi;

	if (units == 'px') {
		// Set pixels mode
		widthEl.removeProperty('step');
		heightEl.removeProperty('step');
		dpiEl.removeProperty('placeholder');
		if (dpiEl.value === ''+PublisherConfig.default_print_dpi) {
			dpiEl.value = '';			
		}

		// Convert values back to pixels
		if (!init && widthEl.value) {
			widthEl.value = Publisher.toPx(parseFloat(widthEl.value), this.previousUnits, dpi) || '';
		}
		if (!init && heightEl.value) {
			heightEl.value = Publisher.toPx(parseFloat(heightEl.value), this.previousUnits, dpi) || '';
		}
	}
	else {
		// Set mm/inches mode
		widthEl.setProperty('step', '0.00001');
		heightEl.setProperty('step', '0.00001');
		dpiEl.setProperty('placeholder', PublisherConfig.default_print_dpi);
		if (!dpiEl.value) {
			dpiEl.value = PublisherConfig.default_print_dpi;
		}

		// Convert values to mm/inches
		if (!init && widthEl.value) {
			var px = Publisher.toPx(parseFloat(widthEl.value), this.previousUnits, dpi);
			widthEl.value = Publisher.fromPx(px, units, dpi) || '';
		}
		if (!init && heightEl.value) {
			var px = Publisher.toPx(parseFloat(heightEl.value), this.previousUnits, dpi);
			heightEl.value = Publisher.fromPx(px, units, dpi) || '';
		}
	}

	this.previousUnits = units;
	if (!init) {
		Publisher.onChange();		
	}
};

Publisher.onPageChanged = function() {
	// Show the correct page in the cropping preview
	if (Publisher.cropSpec) {
		Publisher.cropSpec.page = this.value;
		Publisher.refreshCropImage();
	}
};

Publisher.onFlipChanged = function() {
	// Show the flipped image in the cropping preview
	if (Publisher.cropSpec) {
		Publisher.cropSpec.flip = this.value;
		Publisher.refreshCropImage();
	}
};

Publisher.onRotationChanged = function() {
	// Show the rotated image in the cropping preview
	if (Publisher.cropSpec) {
		Publisher.cropSpec.angle = this.value;
		Publisher.refreshCropImage();
	}
};

Publisher.onFillChanged = function() {
	$('publish_field_autofill').checked = false;
	$('publish_field_transfill').checked = false;
};

Publisher.onAutoFillChanged = function() {
	if (this.checked) {
		$('publish_field_transfill').checked = false;
		$('publish_field_fill').value = '#ffffff';
	}
};

Publisher.onTransFillChanged = function() {
	if (this.checked) {
		$('publish_field_autofill').checked = false;
		$('publish_field_fill').value = '#ffffff';		
	}
};

Publisher.onPublishDownload = function() {
	var dlURL = this.getProperty('data-url');
	if (dlURL)
		window.location = dlURL;
};

Publisher.onPublishTypeChanged = function() {
	Publisher.refreshPublishOutput();
};

Publisher.onChange = function() {
	// Update the image spec from the UI fields
	$$('.publish_field').each(function(el) {
		var set = false;
		if (el.type === "checkbox") {
			if (el.checked) {
				Publisher.imageSpec[el.name] = el.value;
				set = true;
			}
		} else if (el.selectedIndex !== undefined && el.options !== undefined) {
			if ((el.selectedIndex >= 0) && (el.options[el.selectedIndex].value !== '')) {
				Publisher.imageSpec[el.name] = el.options[el.selectedIndex].value;
				set = true;
			}
		} else if (el.value !== '') {
			Publisher.imageSpec[el.name] = el.value;
			set = true;
		}
		
		if (!set) {
			delete Publisher.imageSpec[el.name];
		}
	});

	// TODO Remove things that are the same as the template spec
	// TODO Some things removed below need to stay if they're different from the template
	// TODO ==> add whatever is different to the imageSpec
	// TODO we probably need to get pre-fill the template values in the fields (reverse of the above)
	// TODO fix #2931 as part of this, #3059 is related too

	// Remove default values from the spec, handle special cases 
	if (Publisher.imageSpec.transfill) {
		Publisher.imageSpec.fill = Publisher.imageSpec.transfill;
		delete Publisher.imageSpec.transfill;
	}
	if (Publisher.imageSpec.autofill) {
		Publisher.imageSpec.fill = Publisher.imageSpec.autofill;
		delete Publisher.imageSpec.autofill;
	}
	if (Publisher.imageSpec.fill) {
		if (Publisher.imageSpec.fill.charAt(0) === '#')
			Publisher.imageSpec.fill = Publisher.imageSpec.fill.substring(1);
		if (Publisher.imageSpec.fill === 'ffffff')
			delete Publisher.imageSpec.fill;
	}
	if (Publisher.imageSpec.page === '0' || Publisher.imageSpec.page === '1') {
		delete Publisher.imageSpec.page;
	}
	if (Publisher.imageSpec.halign === 'C0.5') {
		delete Publisher.imageSpec.halign;
	}
	if (Publisher.imageSpec.valign === 'C0.5') {
		delete Publisher.imageSpec.valign;
	}
	if (Publisher.templateSpec.strip && Publisher.templateSpec.strip.value) {
		if (Publisher.imageSpec.strip === '1')
			delete Publisher.imageSpec.strip;
		else
			Publisher.imageSpec.strip = '0';
	}
	if (Publisher.imageSpec.stats === '1') {
		delete Publisher.imageSpec.stats;
	}
	else {
		Publisher.imageSpec.stats = '0';
	}

	// Convert physical sizes back to pixels
	var uEl = $('sizing_units'),
	    units = uEl.options[uEl.selectedIndex].value;
	if (units != 'px') {
		var dpi = parseInt(Publisher.imageSpec.dpi, 10) || PublisherConfig.default_print_dpi;
		if (Publisher.imageSpec.width) {
			Publisher.imageSpec.width = Publisher.toPx(parseFloat(Publisher.imageSpec.width), units, dpi) || 0;
		}
		if (Publisher.imageSpec.height) {
			Publisher.imageSpec.height = Publisher.toPx(parseFloat(Publisher.imageSpec.height), units, dpi) || 0;
		}
	}

	// Update field warnings
	Publisher.refreshWarnings();

	// Update the preview image
	Publisher.refreshPreview();

	// Update the publisher final output
	Publisher.refreshPublishOutput();
};

// Convert val pixels at dpi to mm/inches
Publisher.fromPx = function(val, unit, dpi) {
	var inches = val / dpi;
	switch (unit) {
		case 'px': return val;
		case 'in': return inches.toFixed(3);
		case 'mm': return (inches / 0.0393701).toFixed(3);
		default:   return 0;
	}
};

// Convert val mm/inches to pixels at dpi
Publisher.toPx = function(val, unit, dpi) {
	switch (unit) {
		case 'px': return val;
		case 'in': var inches = val; break;
		case 'mm': var inches = val * 0.0393701; break;
		default:   var inches = 0; break;
	}
	return Math.round(inches * dpi);
};

Publisher.setTemplateInfo = function(el, templateObj) {
	var t = templateObj.template,
	    tempEl = $('publish_field_template'),
	    tempVal = tempEl.options[tempEl.selectedIndex].getProperty('data-id');

	// v2.2 We always use a template
	if (!tempVal) {
		tempVal = ''+PublisherConfig.default_template_id;
	}
	
	// If this data is for the currently selected template
	if (templateObj && (templateObj.id === parseInt(tempVal))) {
		// Save the template spec
		Publisher.templateSpec = t;
		// Show the list of key:value items in the template
		el.empty();
		for (var attr in t) {
			if (t[attr] && t[attr].value !== null && t[attr].value !== '') {
				var attr_name = PublisherText[attr];
				if (attr_name === undefined)
					attr_name = attr.charAt(0).toUpperCase() + attr.substring(1);
				el.grab(new Element('div', {
					'text': attr_name + ' : ' + t[attr].value
				}));
			}
		}
		if (el.getChildren().length === 0) {
			el.set('text', PublisherText.empty);
		}
		// Update field warnings
		Publisher.refreshWarnings();
	}
};

Publisher.refreshPreview = function() {
	var iv = function(v) {
		try { return parseInt(v, 10); }
		catch (e) { return 0; }
	};
	var bv = function(v) {
		return v && (v !== 'false') && (v !== '0');
	};

	// Do not hammer the server
	if (++Publisher.previewImageRC > 1)
		return;

	// Fields we need to override to generate a useful preview
	var skip_fields = ['width', 'height', 'colorspace', 'format', 'attach', 'xref', 'stats'];
	// Copy the image spec to the preview spec, minus the skip fields
	var imageSpec = Publisher.imageSpec,
	    previewSpec = Object.clone(Publisher.previewSpec);
	for (var f in imageSpec) {
		if (!skip_fields.contains(f)) {
			previewSpec[f] = imageSpec[f];
		}
	}

	/* Use the requested format if it's web browser compatible */
	
	if (imageSpec.format &&
	    ['gif', 'jpg', 'jpeg', 'pjpg', 'pjpeg', 'png', 'svg'].contains(imageSpec.format.toLowerCase())) {
		previewSpec.format = imageSpec.format;
	}

	/* Try to reflect aspect ratio and padding of (variable size) final image
	   in the (fixed/restricted size) preview
	*/
	
	// If requested size is smaller than preview, use requested size
	var smaller = false;
	if (iv(imageSpec.width) && (iv(imageSpec.width) <= iv(previewSpec.width))) {
		previewSpec.width = imageSpec.width;
		smaller = !iv(imageSpec.height) || (iv(imageSpec.height) <= iv(previewSpec.height));
	}
	if (iv(imageSpec.height)) {
		if (iv(imageSpec.height) <= iv(previewSpec.height)) {
			previewSpec.height = imageSpec.height;
			smaller = !iv(imageSpec.width) || (iv(imageSpec.width) <= iv(previewSpec.width));
		}
		else {
			smaller = false;
		}
	}
	// If both width and height specified...
	if (iv(imageSpec.width) && iv(imageSpec.height)) {
		if (!smaller) {
			// Fit the image to the preview size
			var aspect = iv(imageSpec.width) / iv(imageSpec.height);
			if (aspect >= 1) {
				previewSpec.height = Math.round(iv(previewSpec.width) / aspect);
			}
			else {
				previewSpec.width = Math.round(iv(previewSpec.height) * aspect);
			}
		}
		// Reflect autosizefit setting
		if (imageSpec.autosizefit === undefined) {
			delete previewSpec.autosizefit;
		}
		// Ignore autocropfit if autosizefit
		if (bv(imageSpec.autosizefit)) {
			delete previewSpec.autocropfit;
		}
	}
	else {
		// If only width or height or neither, ignore autocropfit
		if (bv(imageSpec.autocropfit)) {
			delete previewSpec.autocropfit;
		}
	}

	// Chrome doesn't fire onload if the image src is the same
	var newSrc = Publisher.previewURL + '?' + Object.toQueryString(previewSpec);
	if ($('preview_image').getProperty('src') === newSrc) {
		// But we need to call it so that previewImageRC gets updated
		return Publisher.refreshedPreview();
	}

	// Change the preview image
	$('preview_image').setStyle('display', '');
	$('preview_error').setStyle('display', 'none');
	$('preview_mask').setStyle('display', 'block');
	$('preview_image').setProperty('src', newSrc);
};

Publisher.refreshedPreview = function(error) {
	$('preview_mask').setStyle('display', 'none');
	if (error) {
		$('preview_image').setStyle('display', 'none');
		$('preview_error').setStyle('display', 'block');
	}

	// Decrement the request queue count
	Publisher.previewImageRC = Math.max(--Publisher.previewImageRC, 0);
	// If there is still 1 or more queued request(s), refresh only once
	if (Publisher.previewImageRC > 0) {
		Publisher.previewImageRC = 0;
		Publisher.refreshPreview();
	}
};

Publisher.toggleHelp = function(el) {
	if (Publisher.showingHelp) {
		Publisher.popupHelp.hide();
		Publisher.showingHelp = false;
	}
	else {
		var section = $(el).getProperty('data-anchor'),
		    url = (PublisherConfig.help_url + '#' + section);
		Publisher.popupHelp.showAt(el, url);
		Publisher.showingHelp = true;
	}
	return false;
};

Publisher.initCropping = function() {
	// Remove any previous instance
	if (Publisher.crop !== undefined) {
		$('crop_fix_aspect').removeEvent('change', Publisher.changeAspectRatio);
		$('crop_fix_aspect').selectedIndex = 0;		
		Publisher.crop.destroy();
	}
	// Get default cropping image specs
	var imgSize = $('crop_image').getSize(),
	    imgSrc = $('crop_image').getProperty('src'),
	    urlSep = imgSrc.indexOf('?'),
	    imgParams = imgSrc.substring(urlSep + 1).cleanQueryString().replace(/\+/g, ' ');
	Publisher.cropURL = imgSrc.substring(0, urlSep);
	Publisher.cropSpec = imgParams.parseQueryString();	
	Publisher.cropSize = imgSize;
	Publisher.crop = new Lasso.Crop('crop_image', {
		ratio : false,
		preset : [0, 0, imgSize.x, imgSize.y],
		min : [10, 10],
		handleSize : 10,
		opacity : 0.6,
		color : '#000',
		border : '../static/images/crop.gif',
		onResize : Publisher.updateCrop,
		onComplete : Publisher.endCrop
	});
	$('crop_fix_aspect').addEvent('change', Publisher.changeAspectRatio);
	Publisher.onChange();
};

Publisher.changeAspectRatio = function() {
	var ratio = this.options[this.selectedIndex].value;
	if (!ratio) {
		Publisher.crop.options.ratio = false;
	}
	else {
		Publisher.crop.options.ratio = ratio.split(':');
	}
	Publisher.crop.resetCoords();
	Publisher.crop.setDefault();
	Publisher.onChange();
};

Publisher.updateCrop = function(coords) {
	var ratio = (coords.w && coords.h) ? Math.roundx(coords.w / coords.h, 5) : '&ndash;';
	$('crop_aspect').set('text', ''+ratio);
	$('publish_field_left').value = coords.x > 0 ? Math.roundx(coords.x / Publisher.cropSize.x, 5) : '';
	$('publish_field_top').value = coords.y > 0 ? Math.roundx(coords.y / Publisher.cropSize.y, 5) : '';
	$('publish_field_right').value = ((coords.x + coords.w) < Publisher.cropSize.x) ? Math.roundx((coords.x + coords.w) / Publisher.cropSize.x, 5) : '';
	$('publish_field_bottom').value = ((coords.y + coords.h) < Publisher.cropSize.y) ? Math.roundx((coords.y + coords.h) / Publisher.cropSize.y, 5) : '';
};

Publisher.refreshCropImage = function() {
	// Do not hammer the server
	if (++Publisher.cropImageRC > 1)
		return;

	// Chrome doesn't fire onload if the image src is the same
	var newSrc = Publisher.cropURL + '?' + Object.toQueryString(Publisher.cropSpec)
	if ($('crop_image').getProperty('src') === newSrc) {
		// But we need to call it so that cropImageRC gets updated
		return Publisher.refreshedCropImage();
	}

	// Reloads the crop image with the latest cropSpec.
	// initCropping() is called again (via load event) when the image has loaded.
	$('crop_image').setProperty('src', newSrc);
};

Publisher.refreshedCropImage = function() {
	// Decrement the request queue count
	Publisher.cropImageRC = Math.max(--Publisher.cropImageRC, 0);
	// If there is still 1 or more queued request(s), refresh only once
	if (Publisher.cropImageRC > 0) {
		Publisher.cropImageRC = 0;
		Publisher.refreshCropImage();
	}
};

Publisher.endCrop = function(coords) {
	if (!coords || (!coords.x && !coords.y && !coords.w && !coords.h)) {
		// Crop was cancelled, reset back to initial state
		Publisher.crop.resetCoords();
		Publisher.crop.setDefault();
		coords = Publisher.crop.getRelativeCoords();
	}
	Publisher.updateCrop(coords);
	Publisher.onChange();
};

Publisher.clearWarnings = function() {
	$$('.warning').each(function (el) { el.dispose(); });
};

Publisher.addWarning = function(parentEl, text) {
	var div = new Element('div', { 'class': 'warning' });
	div.grab(new Element('img', { src: PublisherConfig.warn_icon_url }));
	div.grab(new Element('span', { html: text }));
	parentEl.grab(div);
};

Publisher.refreshWarnings = function() {
	Publisher.clearWarnings();

	// Get original file format
	var fileExtension = '';
	if (Publisher.imageSpec.src) {
		var parts = Publisher.imageSpec.src.split('.');
		fileExtension = (parts.length > 1) ? parts.pop().toLowerCase() : '';
	}

	// Get template values
	var t = Publisher.templateSpec,
	    templateFormat = t.format ? t.format.value : '',
	    templateStrip = (t.strip && t.strip.value === true) ? '1' : '0',
	    templateWidth = t.width ? t.width.value : 0,
	    templateHeight = t.height ? t.height.value : 0,
	    templateColorspace = t.colorspace ? t.colorspace.value : '',
	    templateFill = t.fill ? t.fill.value : '';

	// Determine final field values
	var finalFormat = Publisher.imageSpec.format || templateFormat || fileExtension || '',
	    isjpg = ['jpg', 'jpeg', 'pjpg', 'pjpeg'].contains(finalFormat),
	    ispng = ['png'].contains(finalFormat),
	    isgif = ['gif'].contains(finalFormat),
	    istif = ['tif', 'tiff'].contains(finalFormat);

	var finalStrip = Publisher.imageSpec.strip || templateStrip,
	    finalWidth = parseInt(Publisher.imageSpec.width, 10) || templateWidth,
	    finalHeight = parseInt(Publisher.imageSpec.height, 10) || templateHeight,
	    finalColorspace = Publisher.imageSpec.colorspace || templateColorspace,
	    finalFill = Publisher.imageSpec.fill || templateFill;

	// ICC and ICC colorspaces aren't fully integrated with the "final" calculations,
	// but these are only warnings and hopefully the other checks mostly cover it.
	var iccEl = $('publish_field_icc_profile'),
	    iccColorspace = iccEl.options[iccEl.selectedIndex].getProperty('data-colorspace');

	if (PublisherConfig.max_width && (finalWidth > PublisherConfig.max_width)) {
		// Cannot resize larger than original
		Publisher.addWarning($('group_width'), PublisherText.warn_size);		
	}
	if (PublisherConfig.max_height && (finalHeight > PublisherConfig.max_height)) {
		// Cannot resize larger than original
		Publisher.addWarning($('group_height'), PublisherText.warn_size);		
	}
	if (Publisher.imageSpec.icc && !isjpg && !istif) {
		// Not all formats support icc profiles
		Publisher.addWarning($('group_icc'), PublisherText.warn_icc);
	}
	if (finalColorspace) {
		if (finalColorspace !== 'rgb' && !isjpg && !istif) {
			// Not all formats support non-rgb colorspaces
			Publisher.addWarning($('group_colorspace'), PublisherText.warn_colorspace);
		}
		if (Publisher.imageSpec.icc) {
			if (iccColorspace !== finalColorspace) {
				// The final colorspace is different to the icc profile colorspace
				Publisher.addWarning($('group_colorspace'), PublisherText.warn_icc_colorspace);
			}
		}
	}
	if (finalStrip === '1' || finalStrip === true) {
		if (Publisher.imageSpec.icc) {
			// Strip will remove the embedded icc profile
			Publisher.addWarning($('group_strip'), PublisherText.warn_strip);
		}
		if (iccColorspace === 'cmyk' || finalColorspace === 'cmyk') {
			// CMYK usually requires a colour profile
			Publisher.addWarning($('group_strip'), PublisherText.warn_strip_cmyk);
		}
	}
	if ((finalFill === 'none' || finalFill === 'transparent') && !ispng && !isgif) {
		// Not all formats support transparency
		Publisher.addWarning($('group_fill'), PublisherText.warn_transparency);
	}
};

Publisher.refreshPublishOutput = function() {
	var imageSpec = Object.clone(Publisher.imageSpec),
	    internalURL = Publisher.previewURL + '?' + Object.toQueryString(imageSpec),
	    externalURL = Publisher.imageURL + '?' + Object.toQueryString(imageSpec);

	function tidyURL(url) {
		// We can unescape %2F back to / for friendlier URLs
		url = url.replace(/%2F/g, '/');
		// But escape quote chars that would break HTML attrs and JS quoted strings
		return url.replace(/"/g, '%22').replace(/'/g, '%27');
	}
	internalURL = tidyURL(internalURL);
	externalURL = tidyURL(externalURL);

	// Responsive image examples need some kind of sizing
	var respURLs = {},
	    respSizes = [480, 800, 1200];
	for (var i = 0; i < respSizes.length; i++) {
		var size = respSizes[i];
		imageSpec.height = 0;
		imageSpec.width = size;
		respURLs[size] = Publisher.imageURL + '?' + Object.toQueryString(imageSpec);
		respURLs[size] = tidyURL(respURLs[size]);
	}

	// Update download button link
	$('publish_download').setProperty('data-url', internalURL + '&attach=1');

	// Find and render an output template
	var pTypeEl = $('publish_type'),
	    pType = pTypeEl.options[pTypeEl.selectedIndex].value,
	    templateID = 'output_template_' + pType,
	    templateEl = $(templateID);

	var templateVars = {
		'server_url': PublisherConfig.external_server_url,
		'image_url': externalURL,
		'image_url_480': respURLs[480],
		'image_url_800': respURLs[800],
		'image_url_1200': respURLs[1200],
		'static_url': PublisherConfig.external_static_url
	};

	if (templateEl && Publisher.hasOuterHTML) {
		var templateText = templateEl.outerHTML,
		    templateHeader = '<div id="' + templateID + '">',
		    templateFooter = '</div>';
		// Remove header and footer from template text
		templateText = templateText.substring(templateHeader.length, templateText.length - templateFooter.length);
		// Escape HTML tags
		templateText = templateText.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
		// Perform template vars substitution
		for (var k in templateVars) {
			var reKey = new RegExp('\{' + k + '\}', 'g');
			templateText = templateText.replace(reKey, templateVars[k]);
		}
		// Show the result
		$('publish_output').set('html', templateText);
		if (pType !== 'plain') {
			// Invoke highlight.js
			hljs.highlightBlock($('publish_output'));
		}
	}
	else {
		// Template not found or unsupported - just publish the URL as a fallback
		$('publish_output').set('text', templateVars.image_url);
	}
};

// Invoked (by the file selection window) when a file is selected
function onFileSelected(src) {
	$('publish_field_overlay_src').value = src;
	Publisher.onChange();
}

/*** Page initialise ***/

function onInit() {
	GenericPopup.initButtons();
	Publisher.init();
}

window.addEvent('domready', onInit);
