/*!
	Document:      admin.js
	Date started:  30 Oct 2012
	By:            Matt Fozard
	Purpose:       Quru Image Server administration area JS
	Requires:      base.js
	               MooTools More - Fx.Slide, Sortables
	               Picker
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
	01Oct2015  Matt  Added template admin
*/

"use strict";

/*** Generic list pages ***/

var GenericListPage = {};
// Converts all links with the "popuplink" class to launch a popup
GenericListPage.initPopupLinks = function(popupWidth, popupHeight) {
	var editlinks = $$('.popuplink');
	editlinks.each(function(el) {
		popup_convert_anchor(el, popupWidth, popupHeight, function() { window.location.reload(); });
	});
};
// Converts all forms with the "delform" class to perform an
// AJAX delete along with standard event handling
GenericListPage.initDeleteLinks = function(objName) {
	var objNameCap = objName.substring(0, 1).toUpperCase() + objName.substring(1);
	var delforms = $$('.delform');
	delforms.each(function(form) {
		setAjaxJsonForm(form,
			function() {
				return confirm('Are you sure you want to delete ' + objName + ' \'' + form.del_name.value + '\'?');
			},
			null,
			function() {
				alert(objNameCap + ' deleted successfully.');
				window.location.reload();
			},
			function(httpStatus, responseText) {
				var err = getAPIError(httpStatus, responseText);
				alert('Sorry, this ' + objName + ' was not deleted.\n\n' + err.message);
			}
		);
	});
};

/*** Template list page ***/

var TemplateList = {};
TemplateList.onInit = function() {
	GenericListPage.initPopupLinks(575, 650);
	GenericListPage.initDeleteLinks('template');
	setAjaxJsonForm(
		'deftemplform',
		TemplateList.changeDefaultTemplate,
		TemplateList.onDefTemplSubmit,
		TemplateList.onDefTemplSuccess,
		TemplateList.onDefTemplError
	);
};
TemplateList.changeDefaultTemplate = function() {
	return confirm('Are you sure you want to change the default image template?\n\n' +
	               'Some or all of your images may need to be re-generated.');
};
TemplateList.onDefTemplSubmit = function() {
	DataMaintenance.disableButtons();
};
TemplateList.onDefTemplSuccess = function() {
	DataMaintenance.enableButtons();
	window.location.reload();
};
TemplateList.onDefTemplError = function(httpStatus, responseText) {
	DataMaintenance.enableButtons();
	var err = getAPIError(httpStatus, responseText);
	alert('Sorry, your changes were not saved.\n\n' + err.message);
};

/*** User list page ***/

var UserList = {};
UserList.onInit = function() {
	GenericListPage.initPopupLinks(575, 650);
	GenericListPage.initDeleteLinks('user');
};

/*** Group list page ***/

var GroupList = {};
GroupList.onInit = function() {
	GenericListPage.initPopupLinks(700, 650);
	GenericListPage.initDeleteLinks('group');
};

/*** Template edit page ***/

var TemplateEdit = {};
TemplateEdit.onInit = function() {
	GenericPopup.initButtons();
	setAjaxJsonForm(
		'editform',
		TemplateEdit.validate,
		GenericPopup.defaultSubmitting,
		GenericPopup.defaultSubmitSuccess,
		TemplateEdit.onSubmitError
	);
	// These are borrowed from publish.js
	addEventEx('publish_field_fill', 'change', TemplateEdit.onFillChanged);
	addEventEx('publish_field_autofill', 'change', TemplateEdit.onAutoFillChanged);
	addEventEx('publish_field_transfill', 'change', TemplateEdit.onTransFillChanged);
	addEventEx('overlay_src_browse', 'click', TemplateEdit.onBrowseOverlay);
	$$('img.help').each(function(img) {
		addEventEx(img, 'click', function() { TemplateEdit.toggleHelp(img); });
	});
	// Popup help (see preview_popup.js)
	TemplateEdit.popupHelp = new IframePopup(
		$$('.preview_popup')[0], true, function() {
			TemplateEdit.showingHelp = false;
		}
	);
};
TemplateEdit.validate = function() {
	form_clearErrors('editform');
	
	if (validate_isempty('name')) {
		form_setError('name');
		alert('You must enter a name for the template.');
		return false;
	}
	// Ensure numbers are numbers
	$$('.publish_field').each(function(el) {
		if ((el.type === "number") && el.value && isNaN(parseFloat(el.value))) {
			form_setError(el.name);
			alert('The value for ' + el.name + ' must be a number.');
			return false;
		}
	});

	// Populate the 'template' hidden field and allow form submission to continue
	TemplateEdit.setTemplateJSON();
	return true;
};
TemplateEdit.onSubmitError = function(httpStatus, responseText) {
	GenericPopup.enableButtons();
	var err = getAPIError(httpStatus, responseText);
	if (err.status == APICodes.ALREADY_EXISTS) {
		form_setError('name');
		alert('A template with this name already exists, please choose another name.');
	}
	else
		alert('Sorry, your changes were not saved.\n\n' + err.message);
};
TemplateEdit.onFileSelected = function(src) {
	$('publish_field_overlay_src').value = src;	
};
TemplateEdit.setTemplateJSON = function() {
	var values = {};
	// Get all template field values
	$$('.publish_field').each(function(el) {
		var key = el.id.substring(14);  // Strip "publish_field_" from "publish_field_key"
		if (el.type === "checkbox") {
			values[key] = {'value': el.checked};
		} else if (el.type === "number") {
			var nval = (el.value && !isNaN(parseFloat(el.value))) ? parseFloat(el.value) : null;
			values[key] = {'value': nval};
		} else if (el.selectedIndex !== undefined && el.options !== undefined) {
			var sval = (el.selectedIndex >= 0) ? el.options[el.selectedIndex].value : null;
			values[key] = {'value': sval};
		} else {
			values[key] = {'value': el.value};
		}
	});
	// Special field handling - fill
	if (values['autofill']['value']) values['fill']['value'] = 'auto';
	if (values['transfill']['value']) values['fill']['value'] = 'none';
	delete values['autofill'];
	delete values['transfill'];
	// Set template hidden value
	$('template').value = JSON.stringify(values);
};

/* These are borrowed from publish.js
 */
TemplateEdit.onFillChanged = function() {
	$('publish_field_autofill').checked = false;
	$('publish_field_transfill').checked = false;
};
TemplateEdit.onAutoFillChanged = function() {
	if (this.checked) {
		$('publish_field_transfill').checked = false;
		$('publish_field_fill').value = '#ffffff';
	}
};
TemplateEdit.onTransFillChanged = function() {
	if (this.checked) {
		$('publish_field_autofill').checked = false;
		$('publish_field_fill').value = '#ffffff';		
	}
};
TemplateEdit.onBrowseOverlay = function() {
	popup_iframe($(this).getProperty('data-browse-url'), 575, 650);
	return false;
};
TemplateEdit.toggleHelp = function(el) {
	if (TemplateEdit.showingHelp) {
		TemplateEdit.popupHelp.hide();
		TemplateEdit.showingHelp = false;
	}
	else {
		var section = $(el).getProperty('data-anchor'),
		    url = (TemplateAdminConfig.help_url + '#' + section);
		TemplateEdit.popupHelp.showAt(el, url);
		TemplateEdit.showingHelp = true;
	}
	return false;
};

/*** User edit page ***/

var UserEdit = {};
UserEdit.onInit = function() {
	GenericPopup.initButtons();
	setAjaxJsonForm(
		'editform',
		UserEdit.validate,
		GenericPopup.defaultSubmitting,
		GenericPopup.defaultSubmitSuccess,
		UserEdit.onSubmitError
	);
};
UserEdit.validate = function() {
	form_clearErrors('editform');
	
	if (!validate_isempty('email') && !validate_email('email')) {
		form_setError('email');
		alert('The user\'s email address does not appear to be valid.');
		return false;
	}
	if (validate_isempty('username')) {
		form_setError('username');
		alert('You must enter a username for the user.');
		return false;
	}
	if (validate_isempty('password') && ($('editform').user_id.value == '0')) {
		form_setError('password');
		alert('You must enter a password for the user.');
		return false;
	}
	if (!validate_isempty('password') && !validate_length('password', 6)) {
		form_setError('password');
		alert('The user\'s password must be 6 characters or longer.');
		return false;
	}
	return true;
};
UserEdit.onSubmitError = function(httpStatus, responseText) {
	GenericPopup.enableButtons();
	var err = getAPIError(httpStatus, responseText);
	if (err.status == APICodes.ALREADY_EXISTS) {
		form_setError('username');
		alert('This username is already in use, please choose another.');
	}
	else
		alert('Sorry, your changes were not saved.\n\n' + err.message);
};

/*** Group edit page ***/

var GroupEdit = {};
GroupEdit.onInit = function() {
	GenericPopup.initButtons();
	setAjaxJsonForm(
		'editform',
		GroupEdit.validate,
		GenericPopup.defaultSubmitting,
		GroupEdit.onSubmitSuccess,
		GroupEdit.onSubmitError
	);
	// Init drag and drop for group members
	GroupEdit.sortables = new Sortables('#members_in, #members_out', {
		clone: true,
		opacity: 0.5,
		revert: false,
		onComplete: GroupEdit.onDrop
	});
	// Add event handlers
	$$('.member').each(function(el) {
		setDoubleClickHandler(el, function() { GroupEdit.onDoubleClick(el); });
	});
	addEventEx('add_all', 'click', function() { GroupEdit.addRemoveAll(true); });
	addEventEx('remove_all', 'click', function() { GroupEdit.addRemoveAll(false); });
};
GroupEdit.validate = function() {
	form_clearErrors('editform');
	
	if (validate_isempty('name')) {
		form_setError('name');
		alert('You must enter a name for the group.');
		return false;
	}
	return true;
};
GroupEdit.onSubmitSuccess = function(result) {
	if ($('editform').group_id.value > 0)
		GenericPopup.closePage();
	else {
		var newId = result.data.id,
		    pageUrl = window.location.href,
		    redirectUrl = pageUrl.replace('/0/', '/'+newId+'/');
		window.location = redirectUrl;
	}
};
GroupEdit.onSubmitError = function(httpStatus, responseText) {
	GenericPopup.enableButtons();
	var err = getAPIError(httpStatus, responseText);
	if (err.status == APICodes.ALREADY_EXISTS) {
		form_setError('name');
		alert('A group with this name already exists, please choose another name.');
	}
	else
		alert('Sorry, your changes were not saved.\n\n' + err.message);
};
GroupEdit.onDrop = function(draggable) {
	var list = draggable.getParent();
	if (list && (list.id == 'members_in') && (draggable.getProperty('data-member') != 'in')) {
		GroupEdit.updateMember(draggable, 'post');
	}
	else if (list && (list.id == 'members_out') && (draggable.getProperty('data-member') != 'out')) {
		GroupEdit.updateMember(draggable, 'delete');
	}
};
GroupEdit.updateMember = function(el, method) {
	var userId = el.id,
	    form = $('memberform'),
	    url = form.action + (method == 'delete' ? (userId + '/') : ''),
	    dataResult = (method == 'delete' ? 'out' : 'in');
	// Save
	$('members_status').fade('show');
	$('members_status').innerHTML = 'Saving...';
	new Request.JSON({
		url: url,
		method: method,
		emulation: false,
		data: 'user_id=' + userId,
		noCache: true,
		onSuccess: function(jsonObj, jsonText) {
			$('members_status').innerHTML = 'Saved.';
			el.setProperty('data-member', dataResult);
			if (GroupEdit.bulkOpSource != undefined)
				setTimeout(GroupEdit.bulkOp, 1);
			else
				setTimeout(function() { $('members_status').fade('out'); }, 2000);
		},
		onFailure: function(xhr) {
			$('members_status').innerHTML = 'Not saved.';
			var err = getAPIError(xhr.status, xhr.responseText ? xhr.responseText : xhr.statusText);
			alert('Sorry, your changes were not saved.\n\n' + err.message);
			if (GroupEdit.bulkOpSource != undefined)
				setTimeout(GroupEdit.bulkOpEnd, 1);
		}
	}).send();
};
GroupEdit.onDoubleClick = function(draggable) {
	if (draggable.getProperty('data-member') == 'in') {
		$('members_out').grab(draggable);
		GroupEdit.onDrop(draggable);
	}
	else if (draggable.getProperty('data-member') == 'out') {
		$('members_in').grab(draggable);
		GroupEdit.onDrop(draggable);
	}
};
GroupEdit.addRemoveAll = function(add) {
	if (!confirm('Are you sure you want to ' + (add ? 'add all users to the group?' : 'empty the group?')))
		return;
	GroupEdit.bulkOpSource = $(add ? 'members_out' : 'members_in');
	GroupEdit.bulkOpStart();
};
GroupEdit.bulkOpStart = function() {
	$('add_all').disabled = true;
	$('remove_all').disabled = true;
	GroupEdit.sortables.detach();
	GroupEdit.bulkOp();
};
GroupEdit.bulkOpEnd = function() {
	$('add_all').disabled = false;
	$('remove_all').disabled = false;
	GroupEdit.sortables.attach();
	delete GroupEdit.bulkOpSource;
};
GroupEdit.bulkOp = function() {
	// This "find one at a time" method is for iOS, which behaves
	// strangely if we get an array of elements and work from that
	var nextEl = GroupEdit.bulkOpSource.getElement('.member');
	if (nextEl) GroupEdit.onDoubleClick(nextEl);
	else GroupEdit.bulkOpEnd();
};

/*** Data Maintenance page ***/

var DataMaintenance = {};
DataMaintenance.onInit = function() {
	// Add date pickers for input fields
	Locale.use('en-GB');
	new Picker.Date($$('input[type=text]'), {
		timePicker: false,
		positionOffset: {x: 5, y: 0},
		pickerClass: 'picker',
		blockKeydown: false
	});
	// Set form handlers
	setAjaxJsonForm(
		'purge_istats_form',
		DataMaintenance.validateImageStatsPurge,
		DataMaintenance.onTaskSubmit,
		DataMaintenance.onTaskSuccess,
		DataMaintenance.onTaskError
	);
	setAjaxJsonForm(
		'purge_sstats_form',
		DataMaintenance.validateSystemStatsPurge,
		DataMaintenance.onTaskSubmit,
		DataMaintenance.onTaskSuccess,
		DataMaintenance.onTaskError
	);
	setAjaxJsonForm(
		'purge_data_form',
		DataMaintenance.validateDataPurge,
		DataMaintenance.onTaskSubmit,
		DataMaintenance.onTaskSuccess,
		DataMaintenance.onTaskError
	);
	// Add event handlers
	addEventEx('folder_select_button', 'click', DataMaintenance.onFolderSelectClick);
	window.onFolderSelected = function(path) { DataMaintenance.onFolderSelected(path); };
};
DataMaintenance.validateImageStatsPurge = function() {
	return DataMaintenance.validateDate($('purge_istats_text'), $('purge_istats_date'));
};
DataMaintenance.validateSystemStatsPurge = function() {
	return DataMaintenance.validateDate($('purge_sstats_text'), $('purge_sstats_date'));
};
DataMaintenance.validateDate = function(textEl, dateEl) {
	// Validate the UI textual date
	var dVal = Date.parse(textEl.value);
	if (!dVal || !dVal.isValid()) {
		setTimeout(function() {
			textEl.focus();
			textEl.select();
		}, 10);
		return false;
	}
	if (!confirm('Are you sure you want to purge statistics up to ' + textEl.value + ' ?')) {
		return false;
	}
	// Set the hidden date value to submit
	dateEl.value = dVal.toISOString();
	return true;
};
DataMaintenance.validateDataPurge = function() {
	var folder = $('purge_folder_text').innerHTML;
	return confirm('Are you sure you want to purge deleted data in ' + folder + ' and sub-folders?');
};
DataMaintenance.onFolderSelectClick = function() {
	popup_iframe($('folder_browse_url').value, 575, 500);
};
DataMaintenance.onFolderSelected = function(path) {
	$('purge_folder_text').innerHTML = path;
	$('purge_folder_path').value = path;
};
DataMaintenance.onTaskSubmit = function() {
	DataMaintenance.disableButtons();
};
DataMaintenance.onTaskError = function(httpStatus, responseText) {
	DataMaintenance.enableButtons();
	var err = getAPIError(httpStatus, responseText);
	if (err.status == APICodes.ALREADY_EXISTS)
		alert('This task is already running.');
	else
		alert('The task could not be started.\n\n' + err.message);
};
DataMaintenance.onTaskSuccess = function() {
	DataMaintenance.enableButtons();
	alert('The task has been successfully started.');
};
DataMaintenance.enableButtons = function() {
	$$('input[type="submit"]').each(function (el) { el.disabled = false; });
};
DataMaintenance.disableButtons = function() {
	$$('input[type="submit"]').each(function (el) { el.disabled = true; });
};

/*** Folder permissions admin page ***/

var FolderPermissions = {};
FolderPermissions.onInit = function() {
	// Set form handlers
	setAjaxJsonForm(
		'editform',
		FolderPermissions.onFormValidate,
		FolderPermissions.onFormSubmit,
		FolderPermissions.onFormSuccess,
		FolderPermissions.onFormError
	);
	setAjaxJsonForm(
		'deleteform',
		null,
		FolderPermissions.onFormSubmit,
		FolderPermissions.onFormSuccess,
		FolderPermissions.onFormError
	);
	// Add event handlers
	addEventEx('folder_select_button', 'click', FolderPermissions.onFolderSelectClick);
	window.onFolderSelected = function(path) { FolderPermissions.onFolderSelected(path); };
	addEventEx('select_group_id', 'change', FolderPermissions.onGroupSelected);
	addEventEx('edit_perms', 'click', FolderPermissions.onEditClick);
	popup_convert_anchor('trace_permissions', 575, 650);
	// Init permission change slider
	if ($('permissions_edit_container')) {
		FolderPermissions.editSlide = new Fx.Slide('permissions_edit_container').hide();
		$('permissions_edit_container').setStyle('visibility', 'visible');
	}
};
FolderPermissions.onEditClick = function() {
	FolderPermissions.editSlide.toggle();
	return false;
}
FolderPermissions.onFolderSelectClick = function() {
	popup_iframe($('folder_browse_url').value, 575, 500);
};
FolderPermissions.onFolderSelected = function(path) {
	var pageURL = $('permissions_url').value,
	    groupId = $('view_group_id').value;
	FolderPermissions.setLoadingMessage('Please wait...');
	window.location = pageURL + '?path=' + encodeURIComponent(path) + '&group=' + groupId;
};
FolderPermissions.onGroupSelected = function() {
	var pageURL = $('permissions_url').value,
	    folderPath = $('view_folder_path').value,
	    groupEl = $('select_group_id'),
	    groupId = groupEl.options[groupEl.selectedIndex].value;
	FolderPermissions.setLoadingMessage('Please wait...');
	window.location = pageURL + '?path=' + encodeURIComponent(folderPath) + '&group=' + groupId;
};
FolderPermissions.setLoadingMessage = function(msg) {
	$('permissions_edit_container').slide('hide');
	$('permissions_current_container').innerHTML = msg;
};
FolderPermissions.onFormValidate = function() {
	var old_access = $('old_access').value,
	    permission_id = $('view_permission_id').value,
	    accessEl = $('access'),
	    new_access = accessEl.options[accessEl.selectedIndex].value;
	// Continue if there was no permission at all, or if the new value is different
	return (permission_id == '') || (new_access != old_access);
};
FolderPermissions.onFormSubmit = function() {
	DataMaintenance.disableButtons();
};
FolderPermissions.onFormSuccess = function() {
	DataMaintenance.enableButtons();
	window.location.reload();
};
FolderPermissions.onFormError = function(httpStatus, responseText) {
	DataMaintenance.enableButtons();
	var err = getAPIError(httpStatus, responseText);
	alert('Sorry, your changes were not saved.\n\n' + err.message);
};

/*** Folder+User trace permissions page ***/

var TracePermissions = {};
TracePermissions.onInit = function() {
	GenericPopup.initButtons();
	addEventEx('select_user_id', 'change', TracePermissions.onUserSelected);
};
TracePermissions.onUserSelected = function() {
	var pageURL = $('trace_url').value,
	    userEl  = $('select_user_id'),
	    userId  = userEl.options[userEl.selectedIndex].value;
	TracePermissions.setLoadingMessage('Please wait...');
	window.location = pageURL + '&user=' + userId;
};
TracePermissions.setLoadingMessage = function(msg) {
	$('trace_container').innerHTML = msg;
};

/*** Utilities ***/

// Submits the parent of el, invoking the onsubmit event(s) if there are any,
// and cancelling the form submission if any onsubmit handlers return false.
function submitParentForm(el) {
	var f = el.getParent();
	if (f && (f.tagName.toLowerCase() == 'form')) {
		// This is based on MooTools' fireEvent implementation
		var fEvents = f.retrieve('events');
		if (fEvents && fEvents['submit']) {
			var fns = fEvents['submit'].keys;
			for (var i = 0; i < fns.length; i++) {
				if (fns[i]() === false)
					return false;
			}
		}
		// Submit
		f.submit();
	}
	return false;
}

// Invoked (by the file selection window) when a file is selected
function onFileSelected(src) {
	switch ($(document.body).id) {
		case 'template_edit':
			TemplateEdit.onFileSelected(src);
			break;
	}
}

/*** Common page initialise ***/

function onInit() {
	switch ($(document.body).id) {
		case 'template_list':
			TemplateList.onInit();
			break;
		case 'template_edit':
			TemplateEdit.onInit();
			break;
		case 'user_list':
			UserList.onInit();
			break;
		case 'user_edit':
			UserEdit.onInit();
			break;
		case 'group_list':
			GroupList.onInit();
			break;
		case 'group_edit':
			GroupEdit.onInit();
			break;
		case 'data_maintenance':
			DataMaintenance.onInit();
			break;
		case 'folder_permissions':
			FolderPermissions.onInit();
			break;
		case 'trace_permissions':
			TracePermissions.onInit();
			break;
	}
}
window.addEvent('domready', onInit);
