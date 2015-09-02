/*!
	Document:      details_edit.js
	Date started:  09 Feb 2012
	By:            Matt Fozard
	Purpose:       Quru Image Server file details editing helpers
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
*/

function onInit() {
	GenericPopup.initButtons();
	setAjaxJsonForm(
		'editform',
		null,
		GenericPopup.defaultSubmitting,
		GenericPopup.defaultSubmitSuccess,
		GenericPopup.defaultSubmitError
	);
}

window.addEvent('domready', onInit);
