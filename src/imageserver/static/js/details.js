/*!
	Document:      details.js
	Date started:  14 Sep 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server file details helpers
	Requires:      base.js, canvas_view.js
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
	17Jan2013  Matt  Added move, rename, delete actions
	10Jun2013  Matt  Prevent multiple clicks on reset
*/

function onInit() {
	// Enable image zoomer
	if ($('viewport'))
		canvas_view_init('viewport', $('image_url').value);
	
	// Add event handlers
	popup_convert_anchor('edit_attrs', 575, 380, function() { window.location.reload(); });
	popup_convert_anchor('view_stats', 575, 650);
	addEventEx('file_reset', 'click', onResetClick);
	addEventEx('file_rename', 'click', onRenameClick);
	addEventEx('file_move', 'click', onMoveClick);
	addEventEx('file_delete', 'click', onDeleteClick);
	
	// If there is a geo map, enable it
	if (window.init_map)
		init_map();
}

// When Reset menu clicked
function onResetClick() {
	// Reset can take a few seconds, prevent duplicate clicks
	(new Element('span', {
		'html': 'Please wait...',
		'class': 'disabled'
	})).replaces($('file_reset'));
	return true;
}

//Basic validation for folder names
function validateFileName(name) {
	var sep = $('path_sep').value,
	    dotPos = name.indexOf('.');

	if ((name.length < 3) || (dotPos < 1) || (dotPos == (name.length - 1))) {
		alert('The new filename must be in the format: myimage.xyz');
		return false;
	}
	if ((name.indexOf(sep) != -1) || (name.indexOf('..') != -1)) {
		alert('The new filename cannot contain \'' + sep + '\' or \'..\'');
		return false;
	}
	return true;
}

// When Rename menu clicked
function onRenameClick() {
	var oldFilename = $('image_file_name').value;
	var newFilename = prompt('Rename this image file to:', oldFilename);
	if (newFilename)
		newFilename = newFilename.trim();
	if (!newFilename || (newFilename == oldFilename))
		return false;
	
	if (!validateFileName(newFilename)) {
		setTimeout(onRenameClick, 1);
		return false;
	}

	// Rename
	var apiUrl = $('image_admin_url').value,
	    oldPath = $('image_folder_path').value,
	    sep = $('path_sep').value,
	    newPath = join_path(oldPath, newFilename, sep);

	updatePathAsync(
		apiUrl,
		{'path': newPath},
		'The file could not be renamed.'
	);
	return false;
}

// When Delete menu clicked
function onDeleteClick() {
	if (!confirm('Are you sure you want to delete this image?'))
		return false;
	
	// Delete
	var apiUrl = $('image_admin_url').value;
	
	new Request.JSON({
		url: apiUrl,
		method: 'delete',
		emulation: false,
		noCache: true,
		onSuccess: function(jsonObj, jsonText) {
			// Go back to folder
			window.location.href = $('folder_url').value;
		},
		onFailure: function(xhr) {
			var err = getAPIError(xhr.status, xhr.responseText ? xhr.responseText : xhr.statusText);
			alert('The file could not be deleted.\n\n' + err.message);
		}
	}).send();
	return false;
}

// When Move menu clicked
function onMoveClick() {
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
	if (!confirm('Are you sure you want to move this image to ' + path + ' ?'))
		return;
	
	// Move
	var apiUrl = $('image_admin_url').value,
        oldFilename = $('image_file_name').value,
        sep = $('path_sep').value,
        newPath = join_path(path, oldFilename, sep);
	
	updatePathAsync(
		apiUrl,
		{'path': newPath},
		'The file could not be moved.'
	);
}

// Common back-end for renaming and moving files
function updatePathAsync(url, data, errMsg) {
	new Request.JSON({
		url: url,
		method: 'put',
		emulation: false,
		data: data,
		noCache: true,
		onSuccess: function(jsonObj, jsonText) {
			var image = jsonObj.data,
			    url = window.location.href;
			// Reload with the new path
			url = url.substring(0, url.lastIndexOf('src=') + 4);
			window.location.href = url + encodeURIComponent(image.src);
		},
		onFailure: function(xhr) {
			var err = getAPIError(xhr.status, xhr.responseText ? xhr.responseText : xhr.statusText);
			alert(errMsg + '\n\n' + err.message);
		}
	}).send();
}

window.addEvent('domready', onInit);
