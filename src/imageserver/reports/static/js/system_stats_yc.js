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
function onInit(){Locale.use("en-GB");
new Picker.Date($$("input[type=text]"),{timePicker:false,positionOffset:{x:5,y:0},pickerClass:"picker",blockKeydown:false});
$("chartform").addEvent("submit",onSubmit);GenericPopup.initButtons();onSubmit();}function onSubmit(){if(window.chartOptions===undefined){return false;
}var a=$("data_type"),e=$("from_date"),c=$("to_date"),g=Date.parse(e.value),f=Date.parse(c.value);if(!g||!g.isValid()){setTimeout(function(){e.focus();
e.select();},10);return false;}if(!f||!f.isValid()){setTimeout(function(){c.focus();c.select();},10);
return false;}g.set({hr:0,min:0,sec:0,ms:0});f.set({hr:23,min:59,sec:59,ms:999});g=Date.toUTCDate(g);
f=Date.toUTCDate(f);if(chartOptions.tzSeconds){g.setTime(g.getTime()+(chartOptions.tzSeconds*1000));f.setTime(f.getTime()+(chartOptions.tzSeconds*1000));
}var d=chartOptions.dataURL;if(!d){return false;}var h=a.options[a.selectedIndex].value;d+=(d.indexOf("?")==-1?"?":"&");
d+="data_type="+h;d+="&from="+g.toISOString();d+="&to="+f.toISOString();var i="int-positive-units";switch(h){case"100":case"101":case"102":case"4":i="percent";
break;case"6":i="bytes";break;case"7":case"8":i="auto";break;}chartOptions.yAxisType=i;var b=$(chartOptions.container);
if(b){if(!b.chart){initChart(b.id,d,chartOptions.initialHTML,chartOptions.enableZoom,chartOptions.showWeekends,chartOptions.xAxisType,chartOptions.yAxisType,-chartOptions.tzSeconds);
}else{refreshChart(b.id,d,chartOptions.yAxisType);}}return false;}window.addEvent("domready",onInit);
