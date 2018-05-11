/*!
	Document:      playground.js
	Date started:  11 May 2018
	By:            Matt Fozard
	Purpose:       Quru Image Server file details helpers
	Requires:      base.js, common_view.js
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

"use strict";

var Playground = {
	// This is the image to play with
	imageSrc: '',
	// This defines the parameters for the display image
	imageSpec: {}
};

Playground.selectImage = function(imgSrc) {
	var qsIdx = imgSrc.indexOf('?');
	if (qsIdx != -1) {
		Playground.imageSpec = QU.QueryStringToObject(imgSrc.substring(qsIdx + 1), false);
		Playground.imageSrc = Playground.imageSpec.src;
		// TODO delete me
		QU.id('dostuff').innerHTML = 'Doing stuff with '+Playground.imageSrc;
	}
	// Hide image selection area
	var selectionEl = QU.id('pg_selection');
	if (selectionEl) {
		QU.elSetClass(selectionEl, 'selected', true);
		QU.elSetClass(QU.id('pg_main'), 'selected', true);
		// Unhide the image re-select link
		QU.elSetClass(QU.id('pg_reselect'), 'hidden', false);
	}
};

Playground.openImageSelector = function() {
	// Show image selection area
	var selectionEl = QU.id('pg_selection');
	if (selectionEl) {
		QU.elSetClass(selectionEl, 'selected', false);
		QU.elSetClass(QU.id('pg_main'), 'selected', false);
	}
};

Playground.init = function() {
	// Set up image selection
	var thumbs = document.querySelectorAll('.pg_selection img');
	for (var i = 0; i < thumbs.length; i++) {
		thumbs[i].addEventListener('click', function(e) {
			e.preventDefault();
			Playground.selectImage(this.src);
			return false;
		});
	}
	// Set up image re-selection
	var resel = document.querySelector('#pg_reselect a');
	if (resel) {
		resel.addEventListener('click', function(e) {
			e.preventDefault();
			Playground.openImageSelector();
			return false;
		});
	}
};

QU.whenReady(Playground.init);
