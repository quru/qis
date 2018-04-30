/*!
	Document:      account_edit.js
	Date started:  12 Oct 2012
	By:            Matt Fozard
	Purpose:       Quru Image Server user account editing
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
	31Oct2012  Matt  Converted to a GenericPopup
	30Apr2018  Matt  Add password confirmation field
*/

function onInit() {
	GenericPopup.initButtons();
	setAjaxJsonForm(
		'accountform',
		validate,
		GenericPopup.defaultSubmitting,
		GenericPopup.defaultSubmitSuccess,
		onSubmitError
	);
}

function validate() {
	form_clearErrors('accountform');
	
	if (!validate_isempty('email') && !validate_email('email')) {
		form_setError('email');
		alert('Your email address does not appear to be valid.');
		return false;
	}
	if (validate_isempty('username')) {
		form_setError('username');
		alert('You must enter a username for your account.');
		return false;
	}
	if (!validate_isempty('password') && !validate_length('password', 8)) {
		form_setError('password');
		alert('Your new password must be 8 characters or longer.');
		return false;
	}
	if ($2('passwordconf') && $2('password') && $2('passwordconf').value !== $2('password').value) {
		form_setError('password');
		form_setError('passwordconf');
		alert('The passwords entered do not match.');
		return false;
	}
	return true;
}

function onSubmitError(httpStatus, responseText) {
	GenericPopup.enableButtons();

	var obj = getAPIError(httpStatus, responseText);
	if (obj.status == APICodes.ALREADY_EXISTS) {
		form_setError('username');
		alert('This username is already taken, please choose another.');
	}
	else
		alert('Sorry, your changes were not saved.\n\n' + obj.message);
}

window.addEvent('domready', onInit);
