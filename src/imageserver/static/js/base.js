/*!
	Document:      base.js
	Date started:  03 Oct 2012
	By:            Matt Fozard
	Purpose:       Quru Image Server common scripts
	Requires:      MooTools Core 1.3 (no compat),
	               MooTools More 1.3 - Mask
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

/* Image Server API return status values */
APICodes = {
	SUCCESS: 200,
	SUCCESS_TASK_ACCEPTED: 202,
	INVALID_PARAM: 400,
	REQUIRES_AUTH: 401,
	UNAUTHORISED: 403,
	NOT_FOUND: 404,
	ALREADY_EXISTS: 409,
	IMAGE_ERROR: 415,
	INTERNAL_ERROR: 500,
	TOO_BUSY: 503
};

/* Automatically send CSRF token with Ajax calls */
Request.prototype._send = Request.prototype.send;
Request.implement({
    send: function(options){
	var token = $$('meta[name="csrf-token"]')[0];
	if (token) {
	    Object.append(this.headers, {
		'X-CSRF-Token': token.getAttribute('content')
	    });
	}
	return this._send(options)
    }
});

Math.roundx = function(num, places) {
	return Math.round(num * Math.pow(10, places)) / Math.pow(10, places);
};

/* Returns a new "UTC date" from a local timezone date without changing the values.
   Note that d.toString will still give the local timezone, but if you use
   the d.getUTC* and d.toISO* functions they will then do the right thing. */
Date.toUTCDate = function(d) {
	return new Date(Date.UTC(
		d.getFullYear(),
		d.getMonth(),
		d.getDate(),
		d.getHours(),
		d.getMinutes(),
		d.getSeconds(),
		d.getMilliseconds()
	));
};

/* A suite of functionality common to popup edit forms */
GenericPopup = {};
GenericPopup.closePage = function() {
	return popup_close();
};
GenericPopup.initButtons = function() {
	addEventEx('cancel', 'click', GenericPopup.closePage);
	addEventEx('close', 'click', GenericPopup.closePage);
};
GenericPopup.enableButtons = function() {
	$('cancel').disabled = false;
	$('submit').disabled = false;
};
GenericPopup.disableButtons = function() {
	$('cancel').disabled = true;
	$('submit').disabled = true;
};
GenericPopup.defaultSubmitting = function() {
	GenericPopup.disableButtons();
};
GenericPopup.defaultSubmitSuccess = function() {
	GenericPopup.closePage();
};
GenericPopup.defaultSubmitError = function(httpStatus, responseText) {
	GenericPopup.enableButtons();
	var err = getAPIError(httpStatus, responseText);
	alert('Sorry, your changes were not saved.\n\n' + err.message);
};

/* Utility to return whether the client is touch-enabled
 */
function is_touch() {
	return ('ontouchstart' in window) && window.Touch;
}

/* Extended version of the $ function that falls back
 * to finding an element by its form field name.
 */
function $2(element) {
	var el = $(element);
	if (!el && (document.forms.length > 0))
		el = $(document.forms[0].elements[element]);
	return el;
}

/* Invokes el.addEvent only if el (as an element or ID) exists
 */
function addEventEx(el, eventname, fn) {
	if ($(el)) $(el).addEvent(eventname, fn);
}

/* Returns whether a form field is empty */
function validate_isempty(element) {
	var el = $2(element);
	if (el) return el.value.trim().length == 0;
	return true;
}

/* Validates a form field as containing a valid email address */
function validate_email(element) {
	var el = $2(element);
	if (el) {
		var emailFilter=/^([a-zA-Z0-9_=&'\!#\$%\*\/\?\^\{\}\|\~\.\-\+])+\@(([a-zA-Z0-9\-])+\.)+([a-zA-Z0-9]{2,4})+$/;
		return emailFilter.test(el.value);
	}
	return false;
}

/* Validates a form field as containing a value between min and (optionally) max characters */
function validate_length(element, min, max) {
	var el = $2(element);
	if (el) {
		var elval = el.value.trim(),
		    maxOk = (max == undefined) || (max < 1) || (elval.length <= max);
		return maxOk && (elval.length >= min);
	}
	return false;
}

/* Flags an element or form field as an error */
function form_setError(element) {
	var el = $2(element);
	if (el) el.addClass('error');
}

/* Clears the error status from all form fields */
function form_clearErrors(form) {
	form = $(form);
	var elements = $$(form.getElements('input')).append($$(form.getElements('textarea')));
	elements.each(function(el) { el.removeClass('error'); });
}

/* Returns 2 paths (or a path and a filename) joined */
function join_path(path1, path2, sep) {
	// Ensure path1 does not end in sep
	if ((path1 != sep) && (path1.length > 0) && (path1.charAt(path1.length - 1) == sep)) {
		path1 = path1.substring(0, path1.length - 1);
	}
	// Ensure path2 does not start with sep
	if ((path2.length > 0) && (path2.charAt(0) == sep)) {
		path2 = path2.substring(1);
	}
	if ((path1 == sep) || (path1.length == 0) || (path2.length == 0))
		return path1 + path2;
	else
		return path1 + sep + path2;
}

/* Overrides a form's standard behaviour to submit the form asynchronously
 * with an AJAX call, expecting a JSON response. The optional validation 
 * function is called before the form is submitted, and should return true to 
 * continue or false to halt the form submission.
 * 3 events are provided for which you can optionally provide a callback:
 *   onSubmit is called when the form is being submitted (after validation).
 *   onSuccess is called after a successful response with parameters (jsonObject).
 *   onError is called after a failure response with parameters (httpStatus, responseText).
 */
function setAjaxJsonForm(form, validateFn, onSubmitFn, onSuccessFn, onErrorFn) {
	form = $(form);
	if (!form)
		return;
	form.addEvent('submit', function(e) {
		// Cancel standard form submission (e not present if submitting programmatically)
		if (e) e.stop();
		// Validate
		if (validateFn && !validateFn())
			return false;
		// Fire submit event
		if (onSubmitFn)
			onSubmitFn();
		// Send form as AJAX call using MooTools
		new Request.JSON({
			url: form.action,
			method: form.get('_method') ? form.get('_method') : form.method,
			emulation: false,
			data: getFormQueryString(form),
			noCache: true,
			onSuccess: function(jsonObj, jsonText) {
				if (onSuccessFn)
					onSuccessFn(jsonObj);
			},
			onFailure: function(xhr) {
				if (onErrorFn)
					onErrorFn(xhr.status, xhr.responseText ? xhr.responseText : xhr.statusText);
			}
		}).send();
		return false;
	});
}

/* Returns an object of type { status: 500, message: 'An error' }
 * by parsing the expected responses from a system API.
 * Suitable for use in the onError handler for setAjaxJsonForm().
 */
function getAPIError(httpStatus, responseText) {
	return Function.attempt(
		function() {
			if (!responseText)
				throw('Empty JSON');
			else
				return JSON.decode(responseText, true);
		},
		function() {
			if (!httpStatus && !responseText)
				return { status: 0, message: 'The connection was cancelled' };
			else
				return { status: httpStatus, message: 'HTTP Error ' + httpStatus + ' (' + responseText + ')' };
		}
	);
}

/* Returns a query string containing all form input elements and their values.
 * Does not currently support select-many elements.
 */
function getFormQueryString(form) {
	var getstr = '';
	for (var i = 0; i < form.elements.length; i++) {
		var el = form.elements[i];
		
		if ((el.type == 'text') || (el.type == 'hidden') || 
		    (el.type == 'password') || (el.type == 'textarea')) {
			getstr += el.name + '=' + encodeURIComponent(el.value) + '&';
		}
		else if ((el.type == 'checkbox') || (el.type == 'radio')) {
			if (el.checked)
				getstr += el.name + '=' + encodeURIComponent(el.value) + '&';
		}
		else if (el.type == 'select-one') {
			if (el.selectedIndex > -1)
				getstr += el.name + '=' + encodeURIComponent(el.options[el.selectedIndex].value) + '&';
			else
				getstr += el.name + '=&';
		}
	}
	// Remove trailing '&'
	if ((getstr.length > 1) && (getstr.charAt(getstr.length - 1) == '&'))
		getstr = getstr.substring(0, getstr.length-1);
	return getstr;
}

/* Converts an anchor element to launch a popup iFrame on click */
function popup_convert_anchor(element, popupWidth, popupHeight, onCloseFn) {
	var el = $(element);
	if (el && el.tagName == 'A') {
		var url = el.href;
		el.href = '#';
		el.addEvent(is_touch() ? 'touchstart' : 'click', function(e) {
			e.preventDefault();
			return popup_iframe(url, popupWidth, popupHeight, onCloseFn);
		});
	}
}

/* Launches a popup iFrame.
 * The popup height will be reduced if the window height is too small.
 */
function popup_iframe(url, width, height, onCloseFn) {
	var minMargin = 15,
	    winHeight = window.getSize().y,
	    height = Math.min((winHeight - (2 * minMargin)), height),
	    topMargin = Math.max(minMargin, Math.round((winHeight - height) / 2));
	// Define mask event handlers
	var maskKeyUp = function(e) {
		if (window.mask && e.code == 27)
			window.mask.hide();
	};
	// Create popup
	var iframeEl = new Element('iframe', {
		src: url,
		'class': 'edit_popup border',
		styles: {
			top: topMargin + 'px',
			width: width + 'px',
			height: height + 'px',
			'margin-bottom': topMargin + 'px'
		}
	});
	// Show the mask
	var mask = new Mask($(document.body), {
		'class': 'overlay_mask',
		hideOnClick: true,
		destroyOnHide: true
	});
	window.mask = mask;
	window.mask.show();
	// Place the iframe over the mask
	iframeEl.fade('hide');
	$(document.body).grab(iframeEl, 'top');
	iframeEl.fade('in');
	// Enlarge mask if iframe has extended the document body
	window.mask.resize();
	// Handle escape key on mask
	$(document.body).addEvent('keyup', maskKeyUp);
	// Add mask cleanup callback
	mask.addEvent('destroy', function() {
		window.mask = null;
		$(document.body).removeEvent('keyup', maskKeyUp);
		// Close the iframe
		iframeEl.destroy();
		if (onCloseFn != undefined)
			setTimeout(onCloseFn, 1);
	});
	return false;
}

/* Popup/Standalone (dual mode!) page close */
function popup_close() {
	// Support "&onClose=back" and "&onClose=backrefresh" in the URL in popup mode
	var goBack = (window.location.href.indexOf('onClose=back') != -1),
	    goBackRefresh = (window.location.href.indexOf('onClose=backrefresh') != -1);
	
	if (window.parent && window.parent.mask && !goBack)
		window.parent.mask.hide(); // Popup mode close
	else if (goBackRefresh)
		window.location.replace(document.referrer);
	else
		window.history.back();
	return false;
}

/* Opens a "please wait" popup dialog */
function wait_form_open(msg) {
	var minMargin = 15,
	    winHeight = window.getSize().y,
	    approxHeight = 100,
	    topMargin = Math.max(minMargin, Math.round((winHeight / 2) - approxHeight));
	// Create popup
	var divEl = new Element('div', {
		'class': 'edit_popup wait_popup border',
		html: '<img src="../static/images/icon-wait.gif"> &nbsp; ' + msg,
		styles: {
			top: topMargin + 'px',
			width: '400px',
			height: '2.5em',
			'margin-bottom': topMargin + 'px'
		}
	});
	// Show the mask
	var mask = new Mask($(document.body), {
		'class': 'overlay_mask',
		hideOnClick: false,
		destroyOnHide: true
	});
	window.mask = mask;
	window.mask.show();
	// Place the div over the mask
	$(document.body).grab(divEl, 'top');
	// Enlarge mask if div has extended the document body
	window.mask.resize();
	// Add mask cleanup callback
	mask.addEvent('destroy', function() {
		window.mask = null;
		divEl.destroy();
	});
	return false;
}

/* Closes the above */
function wait_form_close() {
	if (window.mask)
		window.mask.hide();
}

/* Adds a double click handler to an element, with emulation for touchscreens */
function setDoubleClickHandler(element, handler) {
	if (is_touch()) {
		element.addEvent('touchstart', function(e) {
			e.preventDefault();
			if (element.lastTapTime != undefined) {
				var timeDiff = Date.now() - element.lastTapTime;
				// iOS 5 fires multiple events so use minimum 10ms time
				if ((timeDiff > 10) && (timeDiff < 1000)) {
					element.lastTapTime = 0;
					handler();
				}
			}
			element.lastTapTime = Date.now();
		});
	}
	else element.addEvent('dblclick', handler);
}

/* Dropdown menu handling */
function dd_menu_init(ownerEl, menuEl) {
	// Init styles
	menuEl.fade('hide');
	// Add click control for touch devices
	ownerEl.addEvent(is_touch() ? 'touchstart' : 'click', function() {
		if (menuEl.opening !== true) {
			menuEl.active = !menuEl.active;
			menuEl.active ? dd_menu_open(menuEl) : dd_menu_close(menuEl);
		}
	});
	// Add rollovers for desktops
	ownerEl.addEvent('mouseenter', function() {
		menuEl.opening = true;
		menuEl.active = true;
		dd_menu_open(menuEl);
		setTimeout(function() { menuEl.opening = false; }, 600);
	});
	ownerEl.addEvent('mouseleave', function() {
		menuEl.opening = false;
		menuEl.active = false;
		setTimeout(function() { dd_menu_close(menuEl); }, 500);
	});
	menuEl.addEvent('mouseenter', function() {
		menuEl.active = true;
	});
	menuEl.addEvent('mouseleave', function() {
		menuEl.active = false;
		setTimeout(function() { dd_menu_close(menuEl); }, 500);
	});
}
function dd_menu_open(menuEl) {
	menuEl.fade('in');
}
function dd_menu_close(menuEl) {
	if (!menuEl.active) {
		menuEl.fade('out');		
	}
}

function base_init_menus() {
	/* Install dropdown menus */
	var owners = $$('.action_menu_owner');
	owners.each(function(el) {
		var menu = $(el.id.substring(0, el.id.indexOf('_owner')));
		if (menu) dd_menu_init(el, menu);
	});
	/* Install special menu handlers */
	popup_convert_anchor('account_menu', 575, 300, function() { window.location.reload(); });
}

window.addEvent('domready', function() {
	base_init_menus();
});
