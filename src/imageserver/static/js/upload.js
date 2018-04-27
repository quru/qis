/*!
	Document:      upload.js
	Date started:  14 Jun 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server File Upload helpers
	Requires:      base.js
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
	22Oct2012  Matt  Converted to use upload JSON API, added HTML5 progress support
	13Jan2015  Matt  Multiple file, drag and drop support
	17Mar2015  Matt  Add folder browse
	27Apr2018  Matt  Allow multiple file drops, appending to upload list
*/

"use strict";

var Upload = {
	enhancedUpload: false,
	droppedFiles: []
};

Upload.init = function () {
	// Add event handlers
	addEventEx('uploadform', 'submit', Upload.onSubmit);
	addEventEx('path', 'keyup', Upload.onPathKey);
	addEventEx('resetfiles', 'click', Upload.onResetFiles);
	addEventEx('resetdir', 'click', Upload.onResetDir);
	addEventEx('folder_browse', 'click', Upload.onFolderBrowse);
	// These don't work via attachEvent for some reason (in Firefox at least)
	$('dropzone').ondragover = Upload.onDragOver;
	$('dropzone').ondragend = Upload.onDragEnd;
	$('dropzone').ondrop = Upload.onDragDrop;
	// Without this, some browsers don't re-enable the button on page refresh
	$('submit').disabled = false;
	// Can we do a fancy upload?
	Upload.enhancedUpload = Upload.isEnhancedUpload();
	if (!Upload.enhancedUpload) {
		$('dropfiles').setStyle('display', 'none');
	}
};

Upload.onResetFiles = function() {
	$('files').value = '';
};

Upload.onResetDir = function() {
	$('directory').value = '';
};

Upload.onResetDropzone = function() {
	$('dropzone').removeClass('active');
	$('dropzone').set('html', 'Drop your files here');
	Upload.droppedFiles = [];
};

Upload.onPathKey = function(e) {
	if (e.code != 9)
		$('path_index_manual').checked = true;
};

Upload.onFolderBrowse = function() {
	$('path_index_manual').checked = true;
	popup_iframe($(this).getProperty('data-browse-url'), 575, 650);
	return false;
};

Upload.onDragOver = function(e) {
	e.stopPropagation();
	e.preventDefault();
	$(this).addClass('active');
};

Upload.onDragEnd = function(e) {
	e.stopPropagation();
	e.preventDefault();	
	$(this).removeClass('active');
};

Upload.onDragDrop = function(e) {
	e.stopPropagation();
	e.preventDefault();

	if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
		// Append non-dupe files to the upload list
		for (var i = 0; i < e.dataTransfer.files.length; i++) {
			var file = e.dataTransfer.files.item(i);
			if (!Upload.fileInList(file, Upload.droppedFiles)) {
				Upload.droppedFiles.push(file);
			}
		}
		$('dropzone').set('html', Upload.droppedFiles.length + ' file' + (Upload.droppedFiles.length > 1 ? 's' : '') + ' dropped');
		
		if (validate_isempty('files') && validate_isempty('directory')) {
			$('selectfiles').addClass('collapse');		
		}
	}
};

Upload.onSubmit = function(e) {
	// Validate form
	if (!Upload.validate())
		return false;
	
	// Show progress
	Upload.setInfo(null);
	Upload.setError(null);
	Upload.setProgress(Upload.enhancedUpload ? 0 : -1);
	$('submit').value = 'Please wait...';
	$('submit').disabled = true;

	// Submit!
	if (Upload.enhancedUpload) {
		// Replace form action with an HTML5 XHR upload
		e.stop();
		Upload.runEnhancedUpload();
		return false;
	}
	else {
		// Continue with standard form post. Listen out for the response.
		$('upload_target').removeEvents('load');
		$('upload_target').addEvent('load', Upload.onIFrameResponse);
		return true;
	}
};

Upload.validate = function() {
	form_clearErrors('uploadform');
	
	if (validate_isempty('files') && validate_isempty('directory') && !Upload.droppedFiles.length) {
		form_setError('files');
		alert('You must select a file to upload');
		return false;
	}
	if ($2('path_index_manual').checked && validate_isempty('path')) {
		form_setError('path');
		alert('You must enter the name of the folder to upload to');
		return false;
	}
	// Dropped files require the HTML5 upload
	if (Upload.droppedFiles.length && !Upload.enhancedUpload) {
		form_setError('files');
		alert('Sorry, your browser cannot upload dropped files.\nPlease use the file selector instead.');
		Upload.onResetDropzone();
		return false;
	}
	
	return true;
};

// When a response has been received
Upload.onResponse = function() {
	$('submit').value = 'Upload complete';
	Upload.setProgress(100);
};

// Legacy form post response - read JSON text from the hidden iframe body content
Upload.onIFrameResponse = function() {
	try {
		Upload.onResponse();
		var ifBody = Upload.getIFrameBody($('upload_target'));
		if (ifBody)
			Upload.onJsonResponse(JSON.decode(ifBody.innerText, true));
	}
	catch (e) { 
		// We don't know whether it worked or not.
	}
};

// Handle form post response
Upload.onJsonResponse = function(jsonObj) {
	Upload.onResponse();

	// Split results into successes, errors
	var images = jsonObj.data,
	    oklist = [],
	    errorlist = [];
	for (var p in images) {
		if (images[p]['error'] !== undefined)
			errorlist.push({filename: p, result: images[p]['error']});
		else
			oklist.push({filename: p, result: images[p]});
	}

	var nexturl = '../uploadcomplete/?nocache=' + String.uniqueID();

	if (jsonObj.status == APICodes.SUCCESS) {
		// Go straight to upload complete page
		window.location.replace(nexturl);
	}
	else {
		// Show one or more errors
		var infomsg = '', errmsg = '',
		    showall = false;

		if (oklist.length > 0) {
			// Some images uploaded, but some didn't
			var plural = (oklist.length > 1) ? ' images were ' : ' image was ';
			infomsg = oklist.length + plural + 'uploaded successfully (<a href="' + nexturl + '">view successful uploads</a>).';
			errmsg =  'But the following problems occurred:<br/>';
			showall = true;
		}
		else {
			if (errorlist.length == 1) {
				// No images uploaded (1 image)
				errmsg = 'Sorry, there was a problem uploading your image:<br/>' + errorlist[0].result.message + '<br/><br/>';
			}
			else {
				// No images uploaded (many images)
				errmsg = 'Sorry, the following problems occurred uploading your images:<br/>';
				showall = true;
			}
		}
		
		if (showall) {
			errmsg += '<ul>\n';
			for (var i = 0; i < errorlist.length; i++) {
				errmsg += '<li><code>' + errorlist[i].filename + '</code> : ' + errorlist[i].result.message + '</li>\n';
			}
			errmsg += '</ul><br/>\n';
		}

		if (infomsg)
			Upload.setInfo(infomsg);
		Upload.setError(errmsg);

		// Reset file selections so the user can try again
		/* #2308 No, leave them alone so the user can try again!
		Upload.onResetDropzone();
		Upload.onResetFiles();
		Upload.onResetDir();
		*/

		// Re-enable the button
		$('submit').value = ' Upload now ';
		$('submit').disabled = false;
		setTimeout(function() { Upload.setProgress(0); }, 1000);
	}
};

// Submits the form using an HTML5 file-upload-capable XHR
Upload.runEnhancedUpload = function() {
	var form = $('uploadform'),
	    formData = new FormData(form),
	    xhr = new XMLHttpRequest();
	
	// Apply dropped files, if any
	for (var i = 0; i < Upload.droppedFiles.length; i++) {
		formData.append('files', Upload.droppedFiles[i]);
	}
	
	// Disable plain text response from the API
	form.api_json_as_text.value = 'false';
	
	xhr.upload.addEventListener('progress', function(e) {
		Upload.setProgress(e.lengthComputable ? Math.round(e.loaded * 100 / e.total) : -1);
	}, false);
	xhr.addEventListener('load', function() {
		Upload.onJsonResponse(getAPIError(xhr.status, xhr.responseText));
	}, false);
	xhr.addEventListener('error', function() {
		Upload.onJsonResponse(getAPIError(xhr.status, xhr.responseText ? xhr.responseText : xhr.statusText));
	}, false);
	xhr.addEventListener('abort', function() {
		Upload.onJsonResponse(getAPIError(xhr.status, 'The upload was interrupted'));
	}, false);
	
	xhr.open(form.method, form.action);
	xhr.send(formData);
};

// Returns whether we can upload the file using an HTML5 XHR with progress events
Upload.isEnhancedUpload = function() {
	var xhr = XMLHttpRequest ? new XMLHttpRequest() : null;
	return (xhr && xhr.upload && (FormData != undefined));
};

// Sets the progress element (if it was rendered) to a value from 0 to 100
// or to the indeterminate state if the value is < 0.
Upload.setProgress = function(percent) {
	if ($('upload_progress')) {
		try {
			if (percent >= 0) $('upload_progress').value = percent;
			else $('upload_progress').removeProperty('value');  // Set as indeterminate
		} catch (e) { }
		try {
			if (percent > 0) $('upload_progress').innerHTML = percent + '%';
			else $('upload_progress').innerHTML = '';
		} catch (e) { }
	}
};

Upload.setMsg = function(el, msg) {
	if (msg) {
		el.setStyle('display', 'block');
		el.set('html', msg);
	}
	else {
		el.setStyle('display', 'none');
	}
};

// Sets or clears the info/error message
Upload.setInfo = function(msg) { Upload.setMsg($('info_msg'), msg); };
Upload.setError = function(msg) { Upload.setMsg($('err_msg'), msg); };

// Utility to return an iframe body element (or null)
Upload.getIFrameBody = function(iframe) {
	var iframeDoc = iframe.contentDocument || iframe.contentWindow.document,
	    iframeBods = iframeDoc.getElementsByTagName('body');
	return (iframeBods.length > 0) ? $(iframeBods[0]) : null;
};

// Utility to return whether a File object is already in a list of File objects
// This is a best guess as not all browsers support the same File object properties
Upload.fileInList = function(file, fileList) {
	if (file && fileList) {
		for (var i = 0; i < fileList.length; i++) {
			var thisFile = fileList[i];
			// Check name property as a minimum
			if (file.name && thisFile.name && file.name === thisFile.name) {
				// Ok they might be the same, try some other properties
				if (file.size && thisFile.size && file.size !== thisFile.size)
					continue;
				if (file.lastModified && thisFile.lastModified && file.lastModified !== thisFile.lastModified)
					continue;
				// They match as far as we can tell
				return true;
			}
		}
	}
	return false;
};

// Invoked (by the folder selection window) when a folder is selected
function onFolderSelected(path) {
	if (path === '/' || path === '\\') {
		path = '';
	}
	form_clearErrors('uploadform');
	$('path').value = path;
}

/*** Page initialise ***/

window.addEvent('domready', Upload.init);
