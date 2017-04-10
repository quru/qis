/*!
	Document:      list.js
	Date started:  07 Jul 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server File Browsing helpers
	Requires:      base.js
	               preview_popup.js
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
	06Oct2015  Matt  Refactored image popup JS into preview_popup.js
*/

"use strict";

function onInit() {
	// Normal browse mode (list.html)
	var previewEl = $$('.preview_popup')[0];
	if (previewEl) {
		var popup = new ImagePopup(previewEl);
		popup.attachToElements('.image_preview');
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
