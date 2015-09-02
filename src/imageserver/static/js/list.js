/*!
	Document:      list.js
	Date started:  07 Jul 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server File Browsing helpers
	Requires:      base.js
	               MooTools Core 1.3 (no compat)
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
	21Sep2011  Matt  Improve popup x position, allow popup to appear under mouse
	                 cursor, prevent hidden popup blocking page elements
	04Apr2012  Matt  Request previews as JPG (fixes previews of PDFs)
	17Jan2013  Matt  Share with folder_list.html
	23Jan2013  Matt  Add folder actions menu handling
	10Feb2015  Matt  Add support for HTTP 202 responses
*/

var previewState = { hoverEl: null, delayId: null, visible: false, mouseOver: false };
var previewUI = { containerEl: null, waitAnimEl: null, imgAreaEl: null, previewEl: null };

function onInit() {
	// Normal browse mode (list.html)
	var previewEl = $('preview_popup');
	if (previewEl) {
		// Add event handlers for producing image previews
		$$('.image_preview').each(function(el) {
			el.addEvent('mouseenter', function() { onMouseIn(el); });
			el.addEvent('mouseleave', function() { onMouseOut(el); });
			el.addEvent('click', function() { onClick(el); });
		});
		
		// Init the preview pane
		if (previewEl.getStyle('visibility') == 'hidden') {
			previewEl.fade('hide');
		}
		previewEl.set('tween', { onComplete: onImagePreviewFadeComplete });
		previewEl.addEvent('mouseenter', onImagePreviewMouseIn);
		previewEl.addEvent('mouseleave', onImagePreviewMouseOut);
		// Grab some UI objects for later
		previewUI.containerEl = previewEl;
		previewUI.waitAnimEl = $('preview_popup_waitimg');
		previewUI.imgAreaEl = $('preview_popup_right');
	}
	
	// Folder browse mode (folder_list.html)
	GenericPopup.initButtons();
	$$('.select_folder').each(function(el) {
		el.addEvent('click', function() {
			onFolderSelectClick(el.getProperty('data-path'));
			return false;
		});
	});
	$$('.select_file').each(function(el) {
		el.addEvent('click', function() {
			onFileSelectClick(el.getProperty('data-path'));
			return false;
		});
	});
	
	// Folder actions (both modes)
	addEventEx('folder_create', 'click', onFolderCreateClick);
	addEventEx('folder_rename', 'click', onFolderRenameClick);
	addEventEx('folder_move', 'click', onFolderMoveClick);
	addEventEx('folder_delete', 'click', onFolderDeleteClick);
}

function onMouseIn(el) {
	// Cancel previous popup if we've moved to a different element
	if (previewState.hoverEl && (previewState.hoverEl != el))
		clearImagePreview();
	// Flag popup to show after a wait
	previewState.hoverEl = el;
	previewState.delayId = doImagePreview.delay(500);
}

function onMouseOut(el) {
	// Bug fix - set a short delay before closing popup in case we're entering the
	// popup (mouseleave on element fires before mouseenter on the popup).
	setTimeout(function() {
		if (!previewState.mouseOver)
			clearImagePreview();
	}, 5);
}

function onClick(el) {
	clearImagePreview();
}

function doImagePreview() {
	// Flag the wait as completed
	previewState.delayId = null;
	
	if (previewState.hoverEl) {
		// Set position of the popup
		var bodyPos = $(document.body).getCoordinates();
		var previewPos = previewUI.containerEl.getCoordinates();
		var targetPos = previewState.hoverEl.getCoordinates();
		var xPos = targetPos.right + 5;
		if ((xPos + previewPos.width) > bodyPos.right)
			xPos = Math.max(targetPos.left + 30, bodyPos.right - previewPos.width);
		var yPos = (targetPos.bottom - (targetPos.height / 2)) - (previewPos.height / 2) + 1;
		previewUI.containerEl.setPosition({ x: xPos, y: yPos });
		// Reset the popup contents
		previewUI.imgAreaEl.empty();
		previewUI.imgAreaEl.grab(previewUI.waitAnimEl);
		previewUI.imgAreaEl.grab(new Element('span')); /* IE<8 trigger line height */
		// Request the preview image async
		previewUI.previewEl = Asset.image(getPreviewImageURL(previewState.hoverEl), {
			onLoad: function() {
				previewUI.imgAreaEl.empty();
				previewUI.imgAreaEl.grab(previewUI.previewEl);
				previewUI.imgAreaEl.grab(new Element('span')); /* IE<8 trigger line height */
			},
			onError: function() {
				previewUI.imgAreaEl.empty();
			}
		});
		// Fade in the popup
		previewState.visible = true;
		previewUI.containerEl.fade('in');
	}
}

function clearImagePreview() {
	// Cancel the popup wait, if there is one in progress
	if (previewState.delayId)
		clearTimeout(previewState.delayId);
	// Hide the popup, if it is visible
	if (previewState.visible)
		previewUI.containerEl.fade('out');
	// Reset state
	previewState.hoverEl = null;
	previewState.delayId = null;
	previewState.visible = false;
	previewState.mouseOver = false;
}

function onImagePreviewMouseIn() {
	previewState.mouseOver = true;
}

function onImagePreviewMouseOut() {
	previewState.mouseOver = false;
	clearImagePreview();
}

function onImagePreviewFadeComplete() {
	// Shift popup somewhere out of the way when hidden
	if (!previewState.visible)
		previewUI.containerEl.setPosition({ x: 1, y: -1000 });
}

function getPreviewImageURL(el) {
	el = $(el);
	// Find nearest anchor
	var aEl = (el.get('tag') == 'a') ? el : el.getParent('a');
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
}

// Invoked in browse mode when a folder is selected
function onFolderSelectClick(path) {
	if (window.parent && window.parent.onFolderSelected) {
		// Pass this on to our host page. Has to be done before we close.
		window.parent.onFolderSelected(path);
	}
	// Close the page
	GenericPopup.closePage();
}
function onFileSelectClick(path) {
	if (window.parent && window.parent.onFileSelected) {
		window.parent.onFileSelected(path);
	}
	GenericPopup.closePage();
}

// Basic validation for folder names
function validateFolderName(name) {
	var sep = $('path_sep').value,
	    dotPos = name.indexOf('.');

	if (dotPos == 0) {
		alert('The folder name cannot start with \'.\'');
		return false;
	}
	if ((name.indexOf(sep) != -1) || (name.indexOf('..') != -1)) {
		alert('The folder name cannot contain \'' + sep + '\' or \'..\'');
		return false;
	}
	return true;
}

// When Create Folder menu clicked
function onFolderCreateClick() {
	var curPath = $('folder_path').value,
	    sep = $('path_sep').value;
	if ((curPath == '') || (curPath == sep))
		var msg = 'Create a new folder called:';
	else
		var msg = 'Create a new folder in ' + curPath + ' called:';
	
	var newName = prompt(msg);
	if (newName)
		newName = newName.trim();
	if (!newName)
		return false;

	if (!validateFolderName(newName)) {
		setTimeout(onFolderCreateClick, 1);
		return false;
	}

	// Create
	var apiUrl = $('folder_admin_create_url').value,
	    newPath = join_path(curPath, newName, sep);
	
	new Request.JSON({
		url: apiUrl,
		method: 'post',
		data: {'path': newPath},
		noCache: true,
		onSuccess: function(jsonObj, jsonText) {
			window.location.reload();
		},
		onFailure: function(xhr) {
			var err = getAPIError(xhr.status, xhr.responseText ? xhr.responseText : xhr.statusText);
			alert('The folder could not be created.\n\n' + err.message);
		}
	}).send();
	return false;
}

// When Rename Folder menu clicked
function onFolderRenameClick() {
	var oldName = $('folder_name').value;
	var newName = prompt('Rename this folder to:', oldName);
	if (newName)
		newName = newName.trim();
	if (!newName || (newName == oldName))
		return false;
	
	// Validate new folder name
	if (!validateFolderName(newName)) {
		setTimeout(onFolderRenameClick, 1);
		return false;
	}
	
	// Rename
	var apiUrl = $('folder_admin_url').value,
	    parentPath = $('parent_folder_path').value,
	    sep = $('path_sep').value,
	    newPath = join_path(parentPath, newName, sep);
	
	updatePathAsync(apiUrl, {'path': newPath}, true);
	return false;
}

// When Move Folder menu clicked
function onFolderMoveClick() {
	// Select destination folder
	popup_iframe($('folder_browse_url').value, 575, 500);
	// The flow continues at onFolderSelected() if a folder is selected
	return false;
}

// Invoked (by the folder selection window) when a folder is selected
function onFolderSelected(path) {
	// Move after a short delay to allow the folder selection window to close
	setTimeout(function() { moveToFolder(path); }, 100);
}

// Invoked when a new folder has been selected
function moveToFolder(path) {
	var oldName = $('folder_name').value;
	if (!confirm('Are you sure you want to move ' + oldName + ' into ' + path + ' ?' +
	    '\n\nAll sub-folders and images will also be moved; this may take a long time.'))
		return;
	
	// Move
	var apiUrl = $('folder_admin_url').value,
        sep = $('path_sep').value,
        newPath = join_path(path, oldName, sep);
	
	updatePathAsync(apiUrl, {'path': newPath}, false);
}

// When Delete Folder menu clicked
function onFolderDeleteClick() {
	var path = $('folder_path').value;
	if (!confirm('Are you sure you want to delete ' + path + ' ?' +
	    '\n\nAll sub-folders and images will also be deleted; this may take a long time.' +
	    '\n\n*** This action cannot be undone! ***'))
		return false;

	wait_form_open('Please wait while the folder is deleted...');

	// Delete
	var apiUrl = $('folder_admin_url').value;

	new Request.JSON({
		url: apiUrl,
		method: 'delete',
		emulation: false,
		noCache: true,
		onSuccess: function(jsonObj, jsonText) {
			wait_form_close();
			if (this.status == APICodes.SUCCESS_TASK_ACCEPTED) {
				alert('This task is taking a long time and will continue in the background.' +
				      '\n\nYou can refresh the page to see when it has completed.');
			}
			// Go back to parent folder
		    var parentPath = $('parent_folder_path').value;
		    changePath(parentPath);
		},
		onFailure: function(xhr) {
			wait_form_close();
			var err = getAPIError(xhr.status, xhr.responseText ? xhr.responseText : xhr.statusText);
			alert('The folder could not be deleted.\n\n' + err.message);
		}
	}).send();
	return false;
}

// Common back-end for renaming and moving folders
function updatePathAsync(url, data, renaming) {
	var opName = renaming ? 'renamed' : 'moved',
	    errMsg = 'The folder could not be ' + opName + '.',
		waitMsg = 'Please wait while the folder is ' + opName + '...';

	wait_form_open(waitMsg);

	new Request.JSON({
		url: url,
		method: 'put',
		emulation: false,
		data: data,
		noCache: true,
		onSuccess: function(jsonObj, jsonText) {
			wait_form_close();
			if (this.status == APICodes.SUCCESS_TASK_ACCEPTED) {
				alert('This task is taking a long time and will continue in the background.' +
				      '\n\nYou can refresh the page to see when it has completed.');
				// Go back to parent folder
				var nextPath = $('parent_folder_path').value;
			}
			else {
				// Go to the new path
				var folder = jsonObj.data,
				    nextPath = encodeURIComponent(folder.path);
			}
			changePath(nextPath);
		},
		onFailure: function(xhr) {
			wait_form_close();
			var err = getAPIError(xhr.status, xhr.responseText ? xhr.responseText : xhr.statusText);
			alert(errMsg + '\n\n' + err.message);
		}
	}).send();
}

// Changes the URL to view a different folder path
function changePath(newPath) {
	var url = window.location.href,
	    piStart = url.lastIndexOf('path='),
	    piEnd = url.indexOf('&', piStart),
	    url2 = url.substring(0, piStart + 5) + newPath;
	if (piEnd != -1)
		url2 += url.substring(piEnd);
	window.location.href = url2;
}

window.addEvent('domready', onInit);
