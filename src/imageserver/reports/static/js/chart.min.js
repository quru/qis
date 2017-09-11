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
var FlotUtil={};
FlotUtil.getWeekendAreas=function(e){var g=(7*24*60*60*1000);var b=(2*24*60*60*1000);var f=new Date(e.xaxis.min);
f.setUTCDate(f.getUTCDate()-((f.getUTCDay()+1)%7));f.setUTCSeconds(0);f.setUTCMinutes(0);f.setUTCHours(0);
var c=f.getTime();var a=[];do{a.push({xaxis:{from:c,to:c+b}});c+=g;}while(c<e.xaxis.max);return a;};FlotUtil.floatFormat=function(c,b){var a=c.toFixed(b);
if((b>0)&&(a.length>=(4+b))&&(parseInt(a.substr(a.length-b))===0)){a=a.substring(0,a.length-(1+b));}return a;
};FlotUtil.byteFormatter=function(b,a){if(b>=1000000000){return FlotUtil.floatFormat(b/1000000000,a.tickDecimals)+" GB";
}else{if(b>=1000000){return FlotUtil.floatFormat(b/1000000,a.tickDecimals)+" MB";}else{if(b>=1000){return FlotUtil.floatFormat(b/1000,a.tickDecimals)+" KB";
}else{return b+" B";}}}};FlotUtil.intFormatter=function(b,a){if(b>=1000000000){return FlotUtil.floatFormat(b/1000000000,a.tickDecimals)+" B";
}else{if(b>=1000000){return FlotUtil.floatFormat(b/1000000,a.tickDecimals)+" M";}else{if(b>=1000){return FlotUtil.floatFormat(b/1000,a.tickDecimals)+" K";
}else{return b;}}}};function Chart(e,h,b,a,g,d,c,f){this.dataURL=h;this.initialHTML=(b?b:"");this.enableZoom=a;
this.showWeekends=g;this.xAxisType=d.toLowerCase();this.yAxisType=c.toLowerCase();this.shiftSeconds=f;
this.plotEl=$(e);this.plotEl.innerHTML=this.initialHTML;this.options={xaxis:this.getAxisConfig(this.xAxisType),yaxis:this.getAxisConfig(this.yAxisType)};
if(this.enableZoom){this.options.selection={mode:"x"};this.plotEl.addEvent("plotselected",function(j,i){this.onChartZoom(j,i);
}.bind(this));}if(this.showWeekends&&(this.xAxisType==="time")){this.options.grid={markings:FlotUtil.getWeekendAreas};
}this.plot=null;this.loadData(this.dataURL);}Chart.prototype.loadData=function(a){new Request.JSON({url:a,method:"get",noCache:true,onSuccess:function(b,c){this.onDataLoaded(b,c);
}.bind(this),onFailure:function(b){this.onDataLoadError(b);}.bind(this)}).get();};Chart.prototype.onDataLoaded=function(b,d){this.data_sets=[b.data];
if(this.xAxisType==="time"&&this.shiftSeconds){var c=this.shiftSeconds*1000,e=this.data_sets[0];for(var a=0;
a<e.length;a++){e[a][0]+=c;}}this.renderChart();};Chart.prototype.onDataLoadError=function(a){this.plotEl.empty();
};Chart.prototype.getAxisConfig=function(a){switch(a){case"time":return{mode:"time",tickLength:5};case"percent":return{min:0,max:100,tickDecimals:0};
case"bytes":return{min:0,tickDecimals:1,minTickSize:1,tickFormatter:FlotUtil.byteFormatter};case"int":return{tickDecimals:0,minTickSize:1};
case"int-positive":return{min:0,tickDecimals:0,minTickSize:1};case"int-units":return{tickDecimals:1,minTickSize:1,tickFormatter:FlotUtil.intFormatter};
case"int-positive-units":return{min:0,tickDecimals:1,minTickSize:1,tickFormatter:FlotUtil.intFormatter};
default:return{};}};Chart.prototype.onChartZoom=function(b,a){Object.append(this.options.xaxis,{min:a.xaxis.from,max:a.xaxis.to});
this.renderChart();};Chart.prototype.renderChart=function(){this.plot=flot.plot(this.plotEl,this.data_sets,this.options);
};Chart.prototype.reset=function(){if(this.plot!=null){delete this.options.xaxis.min;delete this.options.xaxis.max;
this.renderChart();}};function initChart(c,a,i,d,b,f,h,g){var e=$(c);if(e){e.empty();e.chart=new Chart(e,a,i,d,b,f,h,g);
}return false;}function refreshChart(d,e,c){var a=$(d);if(a&&a.chart){var b=a.chart;initChart(d,e,b.initialHTML,b.enableZoom,b.showWeekends,b.xAxisType,c||b.yAxisType,b.shiftSeconds);
}return false;}function resetChart(b){var a=$(b);if(a&&a.chart){a.chart.reset();}return false;}