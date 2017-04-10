/*!
	Document:      preview_popup.js
	Date started:  06 Oct 2015
	By:            Matt Fozard
	Purpose:       Quru Image Server image/iframe preview popup
	Requires:      MooTools Core 1.3 (no compat)
	               MooTools More 1.3 - Assets, String.QueryString
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
	06Oct2015  Matt  Created from bits of list.js and publish.js,
	                 converted functionality to encapsulated classes
*/
"use strict";
function ImagePopup(a){this.previewState={hoverEl:null,delayId:null,visible:false,mouseOver:false};this.previewUI={containerEl:a,waitAnimEl:a.getElement(".preview_popup_waitimg"),imgAreaEl:a.getElement(".preview_popup_right"),contentEl:null};
if(a.getStyle("visibility")==="hidden"){a.fade("hide");}a.set("tween",{onComplete:this.onImagePreviewFadeComplete.bind(this)});
a.addEvent("mouseenter",this.onImagePreviewMouseIn.bind(this));a.addEvent("mouseleave",this.onImagePreviewMouseOut.bind(this));
}ImagePopup.prototype.attachToElements=function(a){$$(a).each(function(b){b.addEvent("mouseenter",function(){this.onElMouseIn(b);
}.bind(this));b.addEvent("mouseleave",function(){this.onElMouseOut(b);}.bind(this));b.addEvent("click",function(){this.onElClick(b);
}.bind(this));}.bind(this));};ImagePopup.prototype.onElMouseIn=function(a){if(this.previewState.hoverEl&&(this.previewState.hoverEl!=a)){this.clearImagePreview();
}this.previewState.hoverEl=a;this.previewState.delayId=setTimeout(function(){this.doImagePreview();}.bind(this),500);
};ImagePopup.prototype.onElMouseOut=function(a){setTimeout(function(){if(!this.previewState.mouseOver){this.clearImagePreview();
}}.bind(this),5);};ImagePopup.prototype.onElClick=function(a){this.clearImagePreview();};ImagePopup.prototype.doImagePreview=function(){this.previewState.delayId=null;
if(this.previewState.hoverEl){var a=$(document.body).getCoordinates();var e=this.previewUI.containerEl.getCoordinates();
var c=this.previewState.hoverEl.getCoordinates();var d=c.right+5;if((d+e.width)>a.right){d=Math.max(c.left+30,a.right-e.width);
}var b=(c.bottom-(c.height/2))-(e.height/2)+1;this.previewUI.containerEl.setPosition({x:d,y:b});this.previewUI.imgAreaEl.empty();
this.previewUI.imgAreaEl.grab(this.previewUI.waitAnimEl);this.previewUI.imgAreaEl.grab(new Element("span"));
this.previewUI.contentEl=Asset.image(this.getPreviewImageURL(this.previewState.hoverEl),{onLoad:function(){this.previewUI.imgAreaEl.empty();
this.previewUI.imgAreaEl.grab(this.previewUI.contentEl);this.previewUI.imgAreaEl.grab(new Element("span"));
}.bind(this),onError:function(){this.previewUI.imgAreaEl.empty();}.bind(this)});this.previewState.visible=true;
this.previewUI.containerEl.fade("in");}};ImagePopup.prototype.clearImagePreview=function(){if(this.previewState.delayId){clearTimeout(this.previewState.delayId);
}if(this.previewState.visible){this.previewUI.containerEl.fade("out");}this.previewState.hoverEl=null;
this.previewState.delayId=null;this.previewState.visible=false;this.previewState.mouseOver=false;};ImagePopup.prototype.onImagePreviewMouseIn=function(){this.previewState.mouseOver=true;
};ImagePopup.prototype.onImagePreviewMouseOut=function(){this.previewState.mouseOver=false;this.clearImagePreview();
};ImagePopup.prototype.onImagePreviewFadeComplete=function(){if(!this.previewState.visible){this.previewUI.containerEl.setPosition({x:1,y:-1000});
}};ImagePopup.prototype.getPreviewImageURL=function(f){f=$(f);var d=(f.get("tag")==="a")?f:f.getParent("a");
if(d==null){return"";}var c=d.href.cleanQueryString().replace(/\+/g," ");var b=c.indexOf("?");var a=c.substring(0,b);
var e=c.substring(b+1).parseQueryString();a=a.replace("details/","image");e.width="200";e.height="200";
e.autosizefit="1";e.stats="0";e.strip="1";e.format="jpg";e.colorspace="srgb";return a+"?"+Object.toQueryString(e);
};function IframePopup(c,b,a){c.addClass("iframe");this.previewUI={containerEl:c,arrowEl:c.getElement(".preview_popup_left"),contentEl:c.getElement(".preview_popup_right")};
this.helpArrowHeight=this.previewUI.arrowEl.getSize().y;this.autoclose=b;this.onclosed=a;if(c.getStyle("visibility")==="hidden"){c.fade("hide");
}}IframePopup.prototype.showAt=function(c,b){var f=$(c).getCoordinates(),e=this.previewUI.containerEl.getCoordinates(),g=f.right,d=(f.bottom-(f.height/2))-(e.height/2)+1;
this.previewUI.arrowEl.setStyle("height",this.helpArrowHeight);if(d<10){var a=10-d;d+=a;this.previewUI.arrowEl.setStyle("height",this.helpArrowHeight-(a*2));
}this.previewUI.containerEl.setPosition({x:g,y:d});this.previewUI.contentEl.empty();this.previewUI.contentEl.grab(new Element("iframe",{src:b}));
this.previewUI.containerEl.fade("in");if(this.autoclose){this.hideFn=this.hideFn||this.hide.bind(this);
setTimeout(function(){$(document.body).addEvent("click",this.hideFn);}.bind(this),1);}};IframePopup.prototype.hide=function(){this.previewUI.containerEl.fade("out");
if(this.autoclose&&this.hideFn){$(document.body).removeEvent("click",this.hideFn);}if(this.onclosed){this.onclosed();
}};