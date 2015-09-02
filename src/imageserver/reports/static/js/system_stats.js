/*!
	Document:      system_stats.js
	Date started:  13 Sep 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server System stats helpers
	Requires:      MooTools Core 1.3 (no compat)
	               MooTools More 1.3 - Date
	               base.js
	               picker.js
	               chart.js
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
	11Feb2015  Matt  #71 Perform timezone conversions client-side
*/

function onInit() {
	// Add date pickers for input fields
	Locale.use('en-GB');
	new Picker.Date($$('input[type=text]'), {
		timePicker: false,
		positionOffset: {x: 5, y: 0},
		pickerClass: 'picker',
		blockKeydown: false
	});
	// Add event handlers
	$('chartform').addEvent('submit', onSubmit);
	// Embedded mode only
	GenericPopup.initButtons();
	// Load initial chart
	onSubmit();
}

function onSubmit() {
	// #71 This should have been created by reports_inc_chart.html
	if (window.chartOptions === undefined)
		return false;

	// Get data filters
	var typeEl = $('data_type'),
	    fromEl = $('from_date'),
	    toEl   = $('to_date'),
	    fromDate = Date.parse(fromEl.value),
	    toDate = Date.parse(toEl.value);
	
	// Validate the 2 dates
	if (!fromDate || !fromDate.isValid()) {
		setTimeout(function() {
			fromEl.focus();
			fromEl.select();
		}, 10);
		return false;
	}
	if (!toDate || !toDate.isValid()) {
		setTimeout(function() {
			toEl.focus();
			toEl.select();
		}, 10);
		return false;
	}
	
	// Set from and to times
	fromDate.set({ 'hr': 0, 'min': 0, 'sec': 0, 'ms': 0 }); 
	toDate.set({ 'hr': 23, 'min': 59, 'sec': 59, 'ms': 999 }); 
	
	// #71 Date.parse returns dates in the browser's time zone.
	//     Remove this so there is no time zone.
	fromDate = Date.toUTCDate(fromDate);
	toDate = Date.toUTCDate(toDate);
	// #71 On the UI we say "times are shown in the server's time zone".
	//     So convert these "server times" to actual UTC for the data API.
	if (chartOptions.tzSeconds) {
		fromDate.setTime(fromDate.getTime() + (chartOptions.tzSeconds * 1000));
		toDate.setTime(toDate.getTime() + (chartOptions.tzSeconds * 1000));
	}
	
	// Check the base URL is known
	var dataURL = chartOptions.dataURL;
	if (!dataURL)
		return false;
	
	// Construct new URL
	var dataType = typeEl.options[typeEl.selectedIndex].value;
	dataURL += (dataURL.indexOf('?') == -1 ? '?' : '&');
	dataURL += 'data_type=' + dataType;
	dataURL += '&from=' + fromDate.toISOString();
	dataURL += '&to=' + toDate.toISOString();
	
	// Determine Y axis required
	var yAxisType = 'int-positive-units';
	switch (dataType) {
		case '100':
		case '101':
		case '102':
		case '4': yAxisType = 'percent'; break;
		case '6': yAxisType = 'bytes'; break;
		case '7':
		case '8': yAxisType = 'auto'; break;
	}
	chartOptions.yAxisType = yAxisType;

	// Create or refresh the chart
	var el = $(chartOptions.container);
	if (el) {
		if (!el.chart) {
			initChart(el.id, dataURL,
				chartOptions.initialHTML,
				chartOptions.enableZoom,
				chartOptions.showWeekends,
				chartOptions.xAxisType,
				chartOptions.yAxisType,
				-chartOptions.tzSeconds
			);
		}
		else {
			refreshChart(el.id, dataURL,
				chartOptions.yAxisType
			);
		}
	}
	return false;
}

window.addEvent('domready', onInit);
