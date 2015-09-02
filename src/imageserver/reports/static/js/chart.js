/*!
	Document:      chart.js
	Date started:  12 Sep 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server Flot charting client
	Requires:      MooTools Core 1.3 (no compat)
	               MooTools More 1.3 - Color
	               MooFlot
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

var FlotUtil = {};

// Helper for returning the weekends in a period
FlotUtil.getWeekendAreas = function(axes) {
	var days7 = (7 * 24 * 60 * 60 * 1000);
	var days2 = (2 * 24 * 60 * 60 * 1000);
	var d = new Date(axes.xaxis.min);
	// go to the first Saturday
	d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 1) % 7))
	d.setUTCSeconds(0);
	d.setUTCMinutes(0);
	d.setUTCHours(0);
	var timems = d.getTime();
	var markings = [];
	do {
		markings.push({ 
			xaxis: { from: timems, to: timems + days2 } 
			// Not setting the yaxis colours all y
		});
		timems += days7;
	} while (timems < axes.xaxis.max);
	
	return markings;
}

// Helper for formatting float values
FlotUtil.floatFormat = function(num, places) {
	var numstr = num.toFixed(places);
	// Convert 'x.0' to 'x' if x >= 100 (or 'x.00' for places 2, etc)
	if ((places > 0) &&
			(numstr.length >= (4 + places)) &&
			(parseInt(numstr.substr(numstr.length - places)) === 0))
		numstr = numstr.substring(0, numstr.length - (1 + places))
	return numstr;
}

// Helper for formatting byte axis values
FlotUtil.byteFormatter = function(val, axis) {
  if (val >= 1000000000)
    return FlotUtil.floatFormat(val / 1000000000, axis.tickDecimals) + ' GB';
  else if (val >= 1000000)
    return FlotUtil.floatFormat(val / 1000000, axis.tickDecimals) + ' MB';
  else if (val >= 1000)
    return FlotUtil.floatFormat(val / 1000, axis.tickDecimals) + ' KB';
  else
    return val + ' B';
}

// Helper for formatting int axis values
FlotUtil.intFormatter = function(val, axis) {
  if (val >= 1000000000)
    return FlotUtil.floatFormat(val / 1000000000, axis.tickDecimals) + ' B';
  else if (val >= 1000000)
    return FlotUtil.floatFormat(val / 1000000, axis.tickDecimals) + ' M';
  else if (val >= 1000)
    return FlotUtil.floatFormat(val / 1000, axis.tickDecimals) + ' K';
  else
    return val;
}


function Chart(containerEl, dataURL, initialHTML, enableZoom, showWeekends, xAxisType, yAxisType, shiftSeconds) {
	// Store properties
	this.dataURL = dataURL;
	this.initialHTML = (initialHTML ? initialHTML : '');
	this.enableZoom = enableZoom;
	this.showWeekends = showWeekends;
	this.xAxisType = xAxisType.toLowerCase();
	this.yAxisType = yAxisType.toLowerCase();
	this.shiftSeconds = shiftSeconds;
	// Get the container element
	this.plotEl = $(containerEl);
	// Set the loading message
	this.plotEl.innerHTML = this.initialHTML;
	// Set the chart options
	this.options = {
//		series: {
//	    lines: { show: true },
//	    points: { show: true }
//    },
		xaxis: this.getAxisConfig(this.xAxisType),
		yaxis: this.getAxisConfig(this.yAxisType)
	};
	if (this.enableZoom) {
		this.options.selection = { mode: 'x' };
		this.plotEl.addEvent('plotselected', function(e, r) { this.onChartZoom(e, r); }.bind(this));
	}
	if (this.showWeekends && (this.xAxisType === 'time')) {
		this.options.grid = { markings: FlotUtil.getWeekendAreas };
	}
	// Set the Flot object
	this.plot = null;
	// Load the data
	this.loadData(this.dataURL);
}

// Asynchronously loads the chart data
Chart.prototype.loadData = function(dataURL) {
	new Request.JSON({
		url: dataURL,
		method: 'get',
		noCache: true,
		onSuccess: function(json, text) { this.onDataLoaded(json, text); }.bind(this),
		onFailure: function(xhr) { this.onDataLoadError(xhr); }.bind(this)
	}).get();
}

// Callback for loaded chart data
Chart.prototype.onDataLoaded = function(json, text) {
	this.data_sets = [json.data];
	// #71 Adjust UTC times back to local time if required
	if (this.xAxisType === 'time' && this.shiftSeconds) {
		var shiftMS = this.shiftSeconds * 1000,
		    set = this.data_sets[0];
		for (var i = 0; i < set.length; i++) {
			set[i][0] += shiftMS;
		}
	}
	this.renderChart();
}

// Callback for data load error
Chart.prototype.onDataLoadError = function(xhr) {
	this.plotEl.empty();
}

// Helper for returning the settings for a chart axis.
// Type can be one from 'auto', 'time', 'percent', 'bytes', 
// 'int', 'int-positive', 'int-units', 'int-positive-units'.
Chart.prototype.getAxisConfig = function(type) {
	switch (type) {
		case 'time':
			return { mode: 'time', tickLength: 5 };
		case 'percent':
			return { min: 0, max: 100, tickDecimals: 0 };
		case 'bytes':
			return { min: 0, tickDecimals: 1, minTickSize: 1, tickFormatter: FlotUtil.byteFormatter };
		case 'int':
			return { tickDecimals: 0, minTickSize: 1 };
		case 'int-positive':
			return { min: 0, tickDecimals: 0, minTickSize: 1 };
		case 'int-units':
			return { tickDecimals: 1, minTickSize: 1, tickFormatter: FlotUtil.intFormatter };
		case 'int-positive-units':
			return { min: 0, tickDecimals: 1, minTickSize: 1, tickFormatter: FlotUtil.intFormatter };
		default:
			return {};
	}
}

// Callback for chart selection
Chart.prototype.onChartZoom = function(event, ranges) {
	Object.append(this.options.xaxis, { min: ranges.xaxis.from, max: ranges.xaxis.to });
	this.renderChart();
}

// (Re-)draws the chart
Chart.prototype.renderChart = function() {
	this.plot = flot.plot(this.plotEl, this.data_sets, this.options);
}

// Resets the zoom level on the chart
Chart.prototype.reset = function() {
	if (this.plot != null) {
		delete this.options.xaxis.min;
		delete this.options.xaxis.max;
		this.renderChart();
	}
}

/* Creates or replaces a chart in a container element, loads the data for the
 * chart via Ajax, and draws the chart on completion.
 * 
 * initialHTML sets the HTML for the container element while the data loads.
 * enableZoom sets whether the chart should allow x-axis click and drag zooming.
 * showWeekends sets whether the chart should colour weekend areas
 *              (when the x-axis type is 'time' only).
 * xAxisType and yAxisType set the mode to use for the axes.
 * 
 * Valid axis types are: 'auto', 'time', 'percent', 'bytes', 
 *                       'int', 'int-positive', 'int-units', 'int-positive-units'
 * shiftSeconds sets the number of seconds to adjust time data by, to display local
 *              times instead of UTC times (when the x-axis type is 'time' only).
 */
function initChart(container_id, dataURL, initialHTML, enableZoom, showWeekends,
                   xAxisType, yAxisType, shiftSeconds) {
	var plotEl = $(container_id);
	if (plotEl) {
		plotEl.empty();
		plotEl.chart = new Chart(plotEl, dataURL, initialHTML, enableZoom, showWeekends,
		                         xAxisType, yAxisType, shiftSeconds);
	}
	return false;
}

/* Updates an existing chart by loading a new data set,
 * and optionally changing the Y axis type to reflect the new values.
 */
function refreshChart(container_id, dataURL, yAxisType) {
	var plotEl = $(container_id);
	if (plotEl && plotEl.chart) {
		var prev = plotEl.chart;
		initChart(container_id, dataURL, prev.initialHTML, prev.enableZoom, prev.showWeekends,
		          prev.xAxisType, yAxisType || prev.yAxisType, prev.shiftSeconds);
	}
	return false;
}

/* Resets a chart (to its original zoom level).
 */
function resetChart(container_id) {
	var plotEl = $(container_id);
	if (plotEl && plotEl.chart)
		plotEl.chart.reset();
	return false;
}
