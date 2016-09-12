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
	06Sep2016  Matt  Default fields to template values on template selection
*/

"use strict";

var Publisher = {
	// Track preview image requests so we don't accidentally hammer the server
	// (e.g. by leaning on the rotation angle increment button)
	previewImageRC: 0,
	cropImageRC: 0,
	// This contains a copy of the base template (full, and just the keys/values)
	templateSpec: {},
	templateSpecKV: {},
	// This defines the parameters for the final image
	imageSpec: {},
	// The preview image uses these too but overrides some (e.g. width and height)
	previewSpec: {}
};

Publisher.init = function() {
	// Add UI event handlers
	addEventEx('crop_image', 'load', Publisher.refreshedCropImage);
	addEventEx('crop_image', 'load', function() { Publisher.resetCropping(true); });
	addEventEx('preview_image', 'load', function() { Publisher.refreshedPreview(false); });
	addEventEx('preview_image', 'error', function() { Publisher.refreshedPreview(true); });
	addEventEx('publish_field_template', 'change', Publisher.onTemplateChanged);
	addEventEx('publish_field_page', 'change', Publisher.onPageChanged);
	addEventEx('publish_field_fill', 'change', Publisher.onFillChanged);
	addEventEx('publish_field_autofill', 'change', Publisher.onAutoFillChanged);
	addEventEx('publish_field_transfill', 'change', Publisher.onTransFillChanged);
	addEventEx('publish_field_flip', 'change', Publisher.onFlipChanged);
	addEventEx('publish_field_rotation', 'change', Publisher.onRotationChanged);
	addEventEx('sizing_units', 'change', function() { Publisher.onUnitsChanged(true); });
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
	Publisher.onUnitsChanged(false);
	Publisher.onTemplateChanged();
	// IE doesn't fire onload if the image was cached and displayed already
	if ($('crop_image').complete) {
		Publisher.resetCropping(false);
	}
};

Publisher.initSpecs = function() {
	var pimgSrc = $('preview_image').getProperty('src'),
	    urlSep = pimgSrc.indexOf('?'),
	    pimgParams = pimgSrc.substring(urlSep + 1).cleanQueryString().replace(/\+/g, ' ');

	// Default the preview image spec (size, format) from the HTML <img>
	Publisher.previewURL = pimgSrc.substring(0, urlSep);
	Publisher.previewSpec = pimgParams.parseQueryString();
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
	Publisher.templateSpecKV = {};
	infoEl.empty();
	infoEl.set('text', PublisherText.loading);

	if (!tempVal) {
		tempVal = PublisherConfig.default_template_id;
	}
	new Request.JSON({
		url: apiURL.replace('/0/', '/' + tempVal + '/'),
		onSuccess: function(jsonObj, jsonText) {
			Publisher.setTemplateInfo(jsonObj.data);
		},
		onFailure: function(xhr) {
			infoEl.set('text', PublisherText.loading_failed);
		}
	}).get();
};

Publisher.onUnitsChanged = function(triggerChange) {
	var dpiEl = $('publish_field_dpi_x'),
	    widthEl = $('publish_field_width'),
	    heightEl = $('publish_field_height'),
	    unitsEl = $('sizing_units'),
	    units = unitsEl.options[unitsEl.selectedIndex].value,
	    dpi = parseInt(dpiEl.value, 10) || PublisherConfig.default_print_dpi,
	    uiChanged = false;

	if (units == 'px') {
		// Set pixels mode
		widthEl.removeProperty('step');
		heightEl.removeProperty('step');
		dpiEl.removeProperty('placeholder');
		if (dpiEl.value === ''+PublisherConfig.default_print_dpi) {
			dpiEl.value = '';
			uiChanged = true;
		}
		// Convert values back to pixels
		if (widthEl.value) {
			widthEl.value = Publisher.toPx(parseFloat(widthEl.value), this.previousUnits, dpi) || '';
			uiChanged = true;
		}
		if (heightEl.value) {
			heightEl.value = Publisher.toPx(parseFloat(heightEl.value), this.previousUnits, dpi) || '';
			uiChanged = true;
		}
	}
	else {
		// Set mm/inches mode
		widthEl.setProperty('step', '0.00001');
		heightEl.setProperty('step', '0.00001');
		dpiEl.setProperty('placeholder', PublisherConfig.default_print_dpi);
		if (!dpiEl.value) {
			dpiEl.value = PublisherConfig.default_print_dpi;
			uiChanged = true;
		}
		// Convert values to mm/inches
		if (widthEl.value) {
			var px = Publisher.toPx(parseFloat(widthEl.value), this.previousUnits, dpi);
			widthEl.value = Publisher.fromPx(px, units, dpi) || '';
			uiChanged = true;
		}
		if (heightEl.value) {
			var px = Publisher.toPx(parseFloat(heightEl.value), this.previousUnits, dpi);
			heightEl.value = Publisher.fromPx(px, units, dpi) || '';
			uiChanged = true;
		}
	}

	this.previousUnits = units;

	if (uiChanged && triggerChange) {
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
		if (el.type === "checkbox") {
			Publisher.imageSpec[el.name] = el.checked ? '1' : '0';
		} else if (el.selectedIndex !== undefined && el.options !== undefined) {
			Publisher.imageSpec[el.name] = el.options[el.selectedIndex].value;
		} else {
			Publisher.imageSpec[el.name] = el.value;
		}
	});

	// Handle special cases
	if (Publisher.imageSpec.transfill === '1') {
		Publisher.imageSpec.fill = 'none';
	}
	if (Publisher.imageSpec.autofill === '1') {
		Publisher.imageSpec.fill = 'auto';
	}
	delete Publisher.imageSpec.transfill;
	delete Publisher.imageSpec.autofill;

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

	// Now remove the values that are the same as the base template
	var ifield, tfield, ival, tval;
	for (ifield in Publisher.imageSpec) {
		tfield = Publisher.webFieldToTemplateKey(ifield);
		ival = Publisher.imageSpec[ifield];
		tval = Publisher.templateSpecKV[tfield];

		// Skip fields
		if (ifield == 'src' || ifield == 'tmp')
			continue;
		// Strings (apart from src) are all case insensitive
		if (typeof ival === 'string')
			ival = ival.toLowerCase();
		if (typeof tval === 'string')
			tval = tval.toLowerCase();
		// Use non-strict equality (for numbers) and check for special cases
		// console.log(ifield + '/' + tfield + ' : image ' + ival + ' vs tmp ' + tval);
		if ((tval == ival) ||
			(!tval && !ival) ||
			(tval === true && ival === '1') ||
			(tval === false && ival === '0') ||
			(tval == null && ival === '0') ||
			(tval == null && ival === '#ffffff')) {
			// Remove from the image URL
			delete Publisher.imageSpec[ifield];
		}
	}

	// Adjust anything that should be different in the image URL
	if (Publisher.imageSpec.tmp === '')
		delete Publisher.imageSpec.tmp;
	if (Publisher.imageSpec.fill && Publisher.imageSpec.fill.charAt(0) === '#')
		Publisher.imageSpec.fill = Publisher.imageSpec.fill.substring(1);

	// Update field warnings
	Publisher.refreshWarnings();

	// Update the preview image
	Publisher.refreshPreview();

	// Update the publisher final output
	Publisher.refreshPublishOutput();
};

Publisher.reset = function(resetTemplate, templateKV) {
	if (templateKV === undefined) {
		templateKV = {};
	}
	var useValue = function(key, defaultValue) {
		var kValue = templateKV[key];
		return ((kValue !== undefined) &&
		        (kValue !== null) &&
		        (kValue !== '') &&
		        (kValue !== 0)) ? kValue : defaultValue;
	};

	// Close help popup
	if (Publisher.showingHelp) {
		Publisher.toggleHelp();
	}

	// Reset all the UI fields (note: the non-image UI fields too)
	$$('label').each(function(el) {
		el.removeClass('highlight');
	});
	$$('input').each(function(el) {
		var key = Publisher.webFieldToTemplateKey(el.name);
		if (el.type === "checkbox") {
			el.checked = (useValue(key, false) === true);
		} else if (el.type === "color") {
			var col = useValue(key, '');
			el.value = (col && col !== 'auto' && col !== 'none') ? col : '#ffffff';
		} else {
			el.value = useValue(key, '');
		}
	});
	$$('select').each(function(el) {
		var key = Publisher.webFieldToTemplateKey(el.name);
		if (key !== 'template' || resetTemplate) {
			var optValue = useValue(key, '');
			if (typeof optValue === 'string')
				optValue = optValue.toLowerCase();
			// Try to match an option
			for (var i = 0; i < el.options.length; i++) {
				if (el.options[i].value.toLowerCase() == optValue) {
					el.selectedIndex = i;
					return;
				}
			}
			// Fall back to selecting the first option
			el.selectedIndex = 0;
		}
	});
	// Handle special cases
	var fillCol = useValue('fill', '');
	if (fillCol === 'auto') {
		$('publish_field_autofill').checked = true;
	}
	if (fillCol === 'none') {
		$('publish_field_transfill').checked = true;		
	}

	// Reset template data fields
	if (resetTemplate) {
		Publisher.templateSpec = {};
		Publisher.templateSpecKV = {};
		$('template_fields').empty();
	}

	// Reset dynamic stuff
	Publisher.clearWarnings();
	Publisher.onUnitsChanged(false);

	// Highlight labels of the fields that we set a value for
	for (var tKey in templateKV) {
		var tValue = useValue(tKey, null);
		if (tValue && (tValue !== '#ffffff')) {
			var fieldEl = $('publish_field_' + tKey);
			if (fieldEl) {
				var labelEl = fieldEl.getParent().getFirst('label');
				if (labelEl)
					labelEl.addClass('highlight');
			}
		}
	}

	// Cropping is a bit of a 'mare as the reset may or may not require us to
	// swap out the old crop image, and (on load at least) the crop image may
	// not even have loaded yet
	var oldCropImageFactors = Publisher.cropSpec ? (Publisher.cropSpec.page + Publisher.cropSpec.flip + Publisher.cropSpec.angle) : NaN;
	// Reset cropping UI (also sets or resets Publisher.cropSpec)
	Publisher.resetCropping(false);
	// Update the crop spec from the new field values
	Publisher.cropSpec.page = $('publish_field_page').value;
	Publisher.cropSpec.flip = $('publish_field_flip').value;
	Publisher.cropSpec.angle = $('publish_field_rotation').value;
	// Now do we need to replace the crop image?
	var newCropImageFactors = (Publisher.cropSpec.page + Publisher.cropSpec.flip + Publisher.cropSpec.angle);
	if (newCropImageFactors !== oldCropImageFactors) {
		Publisher.refreshCropImage();
	}

	// Update the publisher output with new field values
	Publisher.onChange();
};

// Returns the template key for a web parameter name
Publisher.webFieldToTemplateKey = function(param) {
	switch (param) {
		// ImageAttrs
		case 'src': return 'filename';
		case 'tmp': return 'template';
		case 'halign': return 'align_h';
		case 'valign': return 'align_v';
		case 'angle': return 'rotation';
		case 'autocropfit': return 'crop_fit';
		case 'autosizefit': return 'size_fit';
		case 'overlay': return 'overlay_src';
		case 'ovpos': return 'overlay_pos';
		case 'ovsize': return 'overlay_size';
		case 'ovopacity': return 'overlay_opacity';
		case 'icc': return 'icc_profile';
		case 'intent': return 'icc_intent';
		case 'bpc': return 'icc_bpc';
		case 'dpi': return 'dpi_x';
		// TemplateAttrs
		case 'attach': return 'attachment';
		case 'expiry': return 'expiry_secs';
		case 'stats': return 'record_stats';
		// The others are the same
		default: return param;
	}
};

// Convert a template object to a key/value object
// Note that the template keys are not the same as the web parameter names
Publisher.templateToKV = function(templateObj) {
	var kv = {};
	for (var attr in templateObj) {
		kv[attr] = templateObj[attr].value;
	}
	return kv;
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

Publisher.setTemplateInfo = function(templateObj) {
	var t = templateObj.template,
	    infoEl = $('template_fields'),
	    tempEl = $('publish_field_template'),
	    tempVal = tempEl.options[tempEl.selectedIndex].getProperty('data-id');

	// v2.2 We always use a template now
	if (!tempVal) {
		tempVal = ''+PublisherConfig.default_template_id;
	}

	// If this data is for the currently selected template
	if (templateObj && (templateObj.id === parseInt(tempVal))) {
		// Save the template spec
		Publisher.templateSpec = t;
		Publisher.templateSpecKV = Publisher.templateToKV(t);

		// Apply the template values to the UI
		Publisher.reset(false, Publisher.templateSpecKV);

		// Set the template info
		var isDefault = templateObj.id === PublisherConfig.default_template_id;
		infoEl.empty();
		infoEl.set('text', isDefault ? PublisherText.default_template_labels : PublisherText.template_labels);
		infoEl.grab(new Element('br'));
		infoEl.grab(new Element('button', {
			'text': PublisherText.reset_changes,
			'style': 'margin-top: 0.3em',
			'events': {
				'click': function() { Publisher.reset(false, Publisher.templateSpecKV); }
			}
		}));
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
	// Reset previewSpec to its default/starting values
	var imageSpec = Publisher.imageSpec,
	    previewSpec = Object.clone(Publisher.previewSpec),
	    templateSpec = Publisher.templateSpecKV;
	// Copy the image spec to the preview spec, minus the skip fields
	for (var f in imageSpec) {
		if (!skip_fields.contains(f)) {
			previewSpec[f] = imageSpec[f];
		}
	}

	/* Use the requested format if it's web browser compatible */
	
	var reqFormat = (imageSpec.format || templateSpec.format || '').toLowerCase();
	if (['gif', 'jpg', 'jpeg', 'pjpg', 'pjpeg', 'png', 'svg'].contains(reqFormat)) {
		previewSpec.format = reqFormat;
	}

	/* Try to reflect aspect ratio and padding of (variable size) final image
	   in the (fixed/restricted size) preview
	*/
	
	// If requested size is smaller than preview, use requested size
	var imWidth = iv(imageSpec.width) || iv(templateSpec.width) || 0,
	    imHeight = iv(imageSpec.height) || iv(templateSpec.height) || 0,
	    imSizeFit = (imageSpec.autosizefit !== undefined) ? bv(imageSpec.autosizefit) : bv(templateSpec.size_fit),
	    imCropFit = (imageSpec.autocropfit !== undefined) ? bv(imageSpec.autocropfit) : bv(templateSpec.crop_fit),
	    psWidth = iv(previewSpec.width),
	    psHeight = iv(previewSpec.height),
	    smaller = false;

	if (imWidth && (imWidth <= psWidth)) {
		previewSpec.width = imWidth;
		smaller = !imHeight || (imHeight <= psHeight);
	}
	if (imHeight) {
		if (imHeight <= psHeight) {
			previewSpec.height = imHeight;
			smaller = !imWidth || (imWidth <= psWidth);
		}
		else {
			smaller = false;
		}
	}
	// If both width and height are set...
	if (imWidth && imHeight) {
		if (!smaller) {
			// Fit the image to the preview size
			var aspect = imWidth / imHeight;
			if (aspect >= 1) {
				previewSpec.height = Math.round(psWidth / aspect);
			}
			else {
				previewSpec.width = Math.round(psHeight * aspect);
			}
		}
		// Reflect autosizefit setting
		if (!imSizeFit) {
			delete previewSpec.autosizefit;
		}
	}
	else {
		// If only width or height or neither in the final image, autocropfit will be ignored,
		// so delete it from the preview image (which does have both a width and height!)
		if (imCropFit) {
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

Publisher.resetCropping = function(triggerChange) {
	// Remove any previous cropping lasso
	if (Publisher.crop !== undefined) {
		$('crop_fix_aspect').removeEvent('change', Publisher.changeAspectRatio);
		Publisher.crop.destroy();
	}
	// Get default cropping image specs for the latest crop_image
	var imgSize = {
			x: $('crop_image').width,  // Unlike .getSize() this works when the real img is hidden by Lasso.Crop
			y: $('crop_image').height
	    },
	    imgSrc = $('crop_image').getProperty('src'),
	    urlSep = imgSrc.indexOf('?'),
	    imgParams = imgSrc.substring(urlSep + 1).cleanQueryString().replace(/\+/g, ' ');
	Publisher.cropURL = imgSrc.substring(0, urlSep);
	Publisher.cropSpec = imgParams.parseQueryString();
	Publisher.cropSize = imgSize;
	// Create a new cropping lasso
	Publisher.crop = new Lasso.Crop('crop_image', {
		ratio : false,
		preset : Publisher.defaultCropRect(),
		min : [10, 10],
		handleSize : 10,
		opacity : 0.6,
		color : '#000',
		border : '../static/images/crop.gif',
		onResize : Publisher.updateCropFields,
		onComplete : Publisher.endCrop
	});
	// Reset the fixed aspect tool
	$('crop_fix_aspect').selectedIndex = 0;
	$('crop_fix_aspect').addEvent('change', Publisher.changeAspectRatio);
	// Now, Lasso.Crop has called updateCropFields() with rounded ints, which means
	// that top/left/bottom/right are probably showing values with rounding errors.
	// To fix this we'll use the sledgehammer approach.
	Publisher.resetCropFields();

	if (triggerChange) {
		Publisher.onChange();
	}
};

Publisher.defaultCropRect = function() {
	// In v2.2 we have a default crop rectangle that comes from the base template
	if (Publisher.cropSize) {
		var size = Publisher.cropSize,
		    top = Publisher.templateSpecKV.top || 0,
		    left = Publisher.templateSpecKV.left || 0,
		    bottom = Publisher.templateSpecKV.bottom || 1,
		    right = Publisher.templateSpecKV.right || 1;
		// x, y, x2, y2
		return [size.x * left, size.y * top, size.x * right, size.y * bottom];
	}
	return [0, 0, 0, 0];
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

Publisher.resetCropFields = function() {
	// In v2.2 we have a default crop rectangle that comes from the base template
	var top = Publisher.templateSpecKV.top || 0,
        left = Publisher.templateSpecKV.left || 0,
        bottom = Publisher.templateSpecKV.bottom || 1,
        right = Publisher.templateSpecKV.right || 1;
	$('publish_field_left').value = left !== 0 ? Math.roundx(left, 5) : '';
	$('publish_field_top').value = top !== 0 ? Math.roundx(top, 5) : '';
	$('publish_field_right').value = right !== 1 ? Math.roundx(right, 5) : '';
	$('publish_field_bottom').value = bottom !== 1 ? Math.roundx(bottom, 5) : '';
};

Publisher.updateCropFields = function(coords) {
	var ratio = (coords.w && coords.h) ? Math.roundx(coords.w / coords.h, 5) : '&ndash;';
	$('crop_aspect').set('html', ratio);
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
	// Once loaded, resetCropping(true) is called again (via the load event).
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
	Publisher.updateCropFields(coords);
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

window.addEvent('domready', function() {
	GenericPopup.initButtons();
	Publisher.init();
});
