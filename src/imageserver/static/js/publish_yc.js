/*!
	Document:      publish.js
	Date started:  29 Oct 2014
	By:            Matt Fozard
	Purpose:       Quru Image Server image publish wizard
	Requires:      base.js
	               preview_popup.js
	               MooTools More 1.3 - String.QueryString
	               highlight.js
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
	06Oct2015  Matt  Refactored help popup JS into preview_popup.js
*/
"use strict";
var Publisher={previewImageRC:0,cropImageRC:0,imageSpec:{},previewSpec:{}};Publisher.init=function(){addEventEx("crop_image","load",Publisher.refreshedCropImage);
addEventEx("crop_image","load",Publisher.initCropping);addEventEx("preview_image","load",function(){Publisher.refreshedPreview(false);
});addEventEx("preview_image","error",function(){Publisher.refreshedPreview(true);});addEventEx("publish_field_template","change",Publisher.onTemplateChanged);
addEventEx("publish_field_page","change",Publisher.onPageChanged);addEventEx("publish_field_fill","change",Publisher.onFillChanged);
addEventEx("publish_field_autofill","change",Publisher.onAutoFillChanged);addEventEx("publish_field_transfill","change",Publisher.onTransFillChanged);
addEventEx("publish_field_flip","change",Publisher.onFlipChanged);addEventEx("publish_field_rotation","change",Publisher.onRotationChanged);
addEventEx("sizing_units","change",Publisher.onUnitsChanged);addEventEx("overlay_src_browse","click",Publisher.onBrowseOverlay);
addEventEx("publish_download","click",Publisher.onPublishDownload);addEventEx("publish_type","change",Publisher.onPublishTypeChanged);
$$("img.help").each(function(a){addEventEx(a,"click",function(){Publisher.toggleHelp(a);});});$$(".publish_field").each(function(a){addEventEx(a,"change",Publisher.onChange);
});Publisher.popupHelp=new IframePopup($$(".preview_popup")[0],true,function(){Publisher.showingHelp=false;
});Publisher.hasOuterHTML=($("publish_output").outerHTML!==undefined);Publisher.initSpecs();Publisher.onUnitsChanged(null,true);
Publisher.refreshPublishOutput();if($("crop_image").complete){Publisher.initCropping();}};Publisher.initSpecs=function(){var b=$("preview_image").getProperty("src"),a=b.indexOf("?"),c=b.substring(a+1).cleanQueryString().replace(/\+/g," ");
Publisher.previewURL=b.substring(0,a);Publisher.previewSpec=c.parseQueryString();Publisher.previewSpec.cache="0";
Publisher.previewSpec.stats="0";Publisher.imageURL=PublisherConfig.external_image_url;Publisher.imageSpec.src=Publisher.previewSpec.src;
};Publisher.onBrowseOverlay=function(){popup_iframe($(this).getProperty("data-browse-url"),575,650);return false;
};Publisher.onTemplateChanged=function(){var a=$("template_fields"),d=$("publish_field_template"),b=d.options[d.selectedIndex].getProperty("data-id"),c=PublisherConfig.template_api_url;
if(b){a.set("html",PublisherText.loading);(new Request.JSON({url:c.replace("/0/","/"+b+"/"),onSuccess:function(f,e){Publisher.refreshTemplateInfo(a,f);
},onFailure:function(e){a.empty();}})).get();}else{a.empty();}};Publisher.onUnitsChanged=function(d,j){var b=$("publish_field_dpi_x"),g=$("publish_field_width"),h=$("publish_field_height"),a=$("sizing_units"),f=a.options[a.selectedIndex].value,c=parseInt(b.value,10)||PublisherConfig.default_print_dpi;
if(f=="px"){g.removeProperty("step");h.removeProperty("step");b.removeProperty("placeholder");if(b.value===""+PublisherConfig.default_print_dpi){b.value="";
}if(!j&&g.value){g.value=Publisher.toPx(parseFloat(g.value),this.previousUnits,c)||"";}if(!j&&h.value){h.value=Publisher.toPx(parseFloat(h.value),this.previousUnits,c)||"";
}}else{g.setProperty("step","0.00001");h.setProperty("step","0.00001");b.setProperty("placeholder",PublisherConfig.default_print_dpi);
if(!b.value){b.value=PublisherConfig.default_print_dpi;}if(!j&&g.value){var i=Publisher.toPx(parseFloat(g.value),this.previousUnits,c);
g.value=Publisher.fromPx(i,f,c)||"";}if(!j&&h.value){var i=Publisher.toPx(parseFloat(h.value),this.previousUnits,c);
h.value=Publisher.fromPx(i,f,c)||"";}}this.previousUnits=f;if(!j){Publisher.onChange();}};Publisher.onPageChanged=function(){if(Publisher.cropSpec){Publisher.cropSpec.page=this.value;
Publisher.refreshCropImage();}};Publisher.onFlipChanged=function(){if(Publisher.cropSpec){Publisher.cropSpec.flip=this.value;
Publisher.refreshCropImage();}};Publisher.onRotationChanged=function(){if(Publisher.cropSpec){Publisher.cropSpec.angle=this.value;
Publisher.refreshCropImage();}};Publisher.onFillChanged=function(){$("publish_field_autofill").checked=false;
$("publish_field_transfill").checked=false;};Publisher.onAutoFillChanged=function(){if(this.checked){$("publish_field_transfill").checked=false;
$("publish_field_fill").value="#ffffff";}};Publisher.onTransFillChanged=function(){if(this.checked){$("publish_field_autofill").checked=false;
$("publish_field_fill").value="#ffffff";}};Publisher.onPublishDownload=function(){var a=this.getProperty("data-url");
if(a){window.location=a;}};Publisher.onPublishTypeChanged=function(){Publisher.refreshPublishOutput();
};Publisher.onChange=function(){$$(".publish_field").each(function(d){var e=false;if(d.type==="checkbox"){if(d.checked){Publisher.imageSpec[d.name]=d.value;
e=true;}}else{if(d.selectedIndex!==undefined&&d.options!==undefined){if((d.selectedIndex>=0)&&(d.options[d.selectedIndex].value!=="")){Publisher.imageSpec[d.name]=d.options[d.selectedIndex].value;
e=true;}}else{if(d.value!==""){Publisher.imageSpec[d.name]=d.value;e=true;}}}if(!e){delete Publisher.imageSpec[d.name];
}});if(Publisher.imageSpec.transfill){Publisher.imageSpec.fill=Publisher.imageSpec.transfill;delete Publisher.imageSpec.transfill;
}if(Publisher.imageSpec.autofill){Publisher.imageSpec.fill=Publisher.imageSpec.autofill;delete Publisher.imageSpec.autofill;
}if(Publisher.imageSpec.fill){if(Publisher.imageSpec.fill.charAt(0)==="#"){Publisher.imageSpec.fill=Publisher.imageSpec.fill.substring(1);
}if(Publisher.imageSpec.fill==="ffffff"){delete Publisher.imageSpec.fill;}}if(Publisher.imageSpec.page==="0"||Publisher.imageSpec.page==="1"){delete Publisher.imageSpec.page;
}if(Publisher.imageSpec.halign==="C0.5"){delete Publisher.imageSpec.halign;}if(Publisher.imageSpec.valign==="C0.5"){delete Publisher.imageSpec.valign;
}if(PublisherConfig.default_strip){if(Publisher.imageSpec.strip==="1"){delete Publisher.imageSpec.strip;
}else{Publisher.imageSpec.strip="0";}}if(Publisher.imageSpec.stats==="1"){delete Publisher.imageSpec.stats;
}else{Publisher.imageSpec.stats="0";}var a=$("sizing_units"),b=a.options[a.selectedIndex].value;if(b!="px"){var c=parseInt(Publisher.imageSpec.dpi,10)||PublisherConfig.default_print_dpi;
if(Publisher.imageSpec.width){Publisher.imageSpec.width=Publisher.toPx(parseFloat(Publisher.imageSpec.width),b,c)||0;
}if(Publisher.imageSpec.height){Publisher.imageSpec.height=Publisher.toPx(parseFloat(Publisher.imageSpec.height),b,c)||0;
}}Publisher.refreshWarnings();Publisher.refreshPreview();Publisher.refreshPublishOutput();};Publisher.fromPx=function(d,b,a){var c=d/a;
switch(b){case"px":return d;case"in":return c.toFixed(3);case"mm":return(c/0.0393701).toFixed(3);default:return 0;
}};Publisher.toPx=function(d,b,a){switch(b){case"px":return d;case"in":var c=d;break;case"mm":var c=d*0.0393701;
break;default:var c=0;break;}return Math.round(c*a);};Publisher.refreshTemplateInfo=function(d,h){var e=h.data,c=e.template,g=$("publish_field_template"),b=g.options[g.selectedIndex].getProperty("data-id");
if(c&&(e.id===parseInt(b))){delete c.filename;d.empty();for(var a in c){if(c[a]!==null){var f=PublisherText[a];
if(f===undefined){f=a.charAt(0).toUpperCase()+a.substring(1);}d.grab(new Element("div",{id:"template_field_"+a,"data-value":c[a],text:f+": "+c[a]}));
}}if(d.getChildren().length===0){d.set("html",PublisherText.empty);}Publisher.refreshWarnings();}};Publisher.refreshPreview=function(){var c=function(f){try{return parseInt(f,10);
}catch(k){return 0;}};var h=function(f){return f&&(f!=="false")&&(f!=="0");};if(++Publisher.previewImageRC>1){return;
}var b=["width","height","colorspace","format","attach","xref","stats"];var d=Publisher.imageSpec,i=Object.clone(Publisher.previewSpec);
for(var e in d){if(!b.contains(e)){i[e]=d[e];}}if(d.format&&["gif","jpg","jpeg","pjpg","pjpeg","png","svg"].contains(d.format.toLowerCase())){i.format=d.format;
}var g=false;if(c(d.width)&&(c(d.width)<=c(i.width))){i.width=d.width;g=!c(d.height)||(c(d.height)<=c(i.height));
}if(c(d.height)){if(c(d.height)<=c(i.height)){i.height=d.height;g=!c(d.width)||(c(d.width)<=c(i.width));
}else{g=false;}}if(c(d.width)&&c(d.height)){if(!g){var a=c(d.width)/c(d.height);if(a>=1){i.height=Math.round(c(i.width)/a);
}else{i.width=Math.round(c(i.height)*a);}}if(d.autosizefit===undefined){delete i.autosizefit;}if(h(d.autosizefit)){delete i.autocropfit;
}}else{if(h(d.autocropfit)){delete i.autocropfit;}}var j=Publisher.previewURL+"?"+Object.toQueryString(i);
if($("preview_image").getProperty("src")===j){return Publisher.refreshedPreview();}$("preview_image").setStyle("display","");
$("preview_error").setStyle("display","none");$("preview_mask").setStyle("display","block");$("preview_image").setProperty("src",j);
};Publisher.refreshedPreview=function(a){$("preview_mask").setStyle("display","none");if(a){$("preview_image").setStyle("display","none");
$("preview_error").setStyle("display","block");}Publisher.previewImageRC=Math.max(--Publisher.previewImageRC,0);
if(Publisher.previewImageRC>0){Publisher.previewImageRC=0;Publisher.refreshPreview();}};Publisher.toggleHelp=function(b){if(Publisher.showingHelp){Publisher.popupHelp.hide();
Publisher.showingHelp=false;}else{var c=$(b).getProperty("data-anchor"),a=(PublisherConfig.help_url+"#"+c);
Publisher.popupHelp.showAt(b,a);Publisher.showingHelp=true;}return false;};Publisher.initCropping=function(){if(Publisher.crop!==undefined){$("crop_fix_aspect").removeEvent("change",Publisher.changeAspectRatio);
$("crop_fix_aspect").selectedIndex=0;Publisher.crop.destroy();}var c=$("crop_image").getSize(),b=$("crop_image").getProperty("src"),a=b.indexOf("?"),d=b.substring(a+1).cleanQueryString().replace(/\+/g," ");
Publisher.cropURL=b.substring(0,a);Publisher.cropSpec=d.parseQueryString();Publisher.cropSize=c;Publisher.crop=new Lasso.Crop("crop_image",{ratio:false,preset:[0,0,c.x,c.y],min:[10,10],handleSize:10,opacity:0.6,color:"#000",border:"../static/images/crop.gif",onResize:Publisher.updateCrop,onComplete:Publisher.endCrop});
$("crop_fix_aspect").addEvent("change",Publisher.changeAspectRatio);Publisher.onChange();};Publisher.changeAspectRatio=function(){var a=this.options[this.selectedIndex].value;
if(!a){Publisher.crop.options.ratio=false;}else{Publisher.crop.options.ratio=a.split(":");}Publisher.crop.resetCoords();
Publisher.crop.setDefault();Publisher.onChange();};Publisher.updateCrop=function(b){var a=(b.w&&b.h)?Math.roundx(b.w/b.h,5):"&ndash;";
$("crop_aspect").set("html",""+a);$("publish_field_left").value=b.x>0?Math.roundx(b.x/Publisher.cropSize.x,5):"";
$("publish_field_top").value=b.y>0?Math.roundx(b.y/Publisher.cropSize.y,5):"";$("publish_field_right").value=((b.x+b.w)<Publisher.cropSize.x)?Math.roundx((b.x+b.w)/Publisher.cropSize.x,5):"";
$("publish_field_bottom").value=((b.y+b.h)<Publisher.cropSize.y)?Math.roundx((b.y+b.h)/Publisher.cropSize.y,5):"";
};Publisher.refreshCropImage=function(){if(++Publisher.cropImageRC>1){return;}var a=Publisher.cropURL+"?"+Object.toQueryString(Publisher.cropSpec);
if($("crop_image").getProperty("src")===a){return Publisher.refreshedCropImage();}$("crop_image").setProperty("src",a);
};Publisher.refreshedCropImage=function(){Publisher.cropImageRC=Math.max(--Publisher.cropImageRC,0);if(Publisher.cropImageRC>0){Publisher.cropImageRC=0;
Publisher.refreshCropImage();}};Publisher.endCrop=function(a){if(!a||(!a.x&&!a.y&&!a.w&&!a.h)){Publisher.crop.resetCoords();
Publisher.crop.setDefault();a=Publisher.crop.getRelativeCoords();}Publisher.updateCrop(a);Publisher.onChange();
};Publisher.clearWarnings=function(){$$(".warning").each(function(a){a.dispose();});};Publisher.addWarning=function(a,b){var c=new Element("div",{"class":"warning"});
c.grab(new Element("img",{src:PublisherConfig.warn_icon_url}));c.grab(new Element("span",{html:b}));a.grab(c);
};Publisher.refreshWarnings=function(){Publisher.clearWarnings();var r="";if(Publisher.imageSpec.src){var p=Publisher.imageSpec.src.split(".");
r=(p.length>1)?p.pop().toLowerCase():"";}var e="",g="",f="",b="",o="",a="";if($("template_field_format")){e=$("template_field_format").getProperty("data-value");
}if($("template_field_strip")){g=($("template_field_strip").getProperty("data-value")==="true")?"1":"0";
}if($("template_field_width")){f=$("template_field_width").getProperty("data-value");}if($("template_field_height")){b=$("template_field_height").getProperty("data-value");
}if($("template_field_colorspace")){o=$("template_field_colorspace").getProperty("data-value");}if($("template_field_fill")){a=$("template_field_fill").getProperty("data-value");
}var s=Publisher.imageSpec.format||e||PublisherConfig.default_format||r||"",j=["jpg","jpeg","pjpg","pjpeg"].contains(s),c=["png"].contains(s),h=["gif"].contains(s),q=["tif","tiff"].contains(s);
var k=Publisher.imageSpec.strip||g||PublisherConfig.default_strip,l=parseInt(Publisher.imageSpec.width,10)||parseInt(f,10)||0,m=parseInt(Publisher.imageSpec.height,10)||parseInt(b,10)||0,n=Publisher.imageSpec.colorspace||o,t=Publisher.imageSpec.fill||a;
var i=$("publish_field_icc_profile"),d=i.options[i.selectedIndex].getProperty("data-colorspace");if(PublisherConfig.max_width&&(l>PublisherConfig.max_width)){Publisher.addWarning($("group_width"),PublisherText.warn_size);
}if(PublisherConfig.max_height&&(m>PublisherConfig.max_height)){Publisher.addWarning($("group_height"),PublisherText.warn_size);
}if(Publisher.imageSpec.icc&&!j&&!q){Publisher.addWarning($("group_icc"),PublisherText.warn_icc);}if(n){if(n!=="rgb"&&!j&&!q){Publisher.addWarning($("group_colorspace"),PublisherText.warn_colorspace);
}if(Publisher.imageSpec.icc){if(d!==n){Publisher.addWarning($("group_colorspace"),PublisherText.warn_icc_colorspace);
}}}if(k==="1"||k===true){if(Publisher.imageSpec.icc){Publisher.addWarning($("group_strip"),PublisherText.warn_strip);
}if(d==="cmyk"||n==="cmyk"){Publisher.addWarning($("group_strip"),PublisherText.warn_strip_cmyk);}}if((t==="none"||t==="transparent")&&!c&&!h){Publisher.addWarning($("group_fill"),PublisherText.warn_transparency);
}};Publisher.refreshPublishOutput=function(){var f=Publisher.previewURL+"?"+Object.toQueryString(Publisher.imageSpec),h=Publisher.imageURL+"?"+Object.toQueryString(Publisher.imageSpec);
f=f.replace(/%2F/g,"/");h=h.replace(/%2F/g,"/");f=f.replace(/"/g,"%22").replace(/'/g,"%27");h=h.replace(/"/g,"%22").replace(/'/g,"%27");
$("publish_download").setProperty("data-url",f+"&attach=1");var a=$("publish_type"),c=a.options[a.selectedIndex].value,i="output_template_"+c,b=$(i);
var e={server_url:PublisherConfig.external_server_url,image_url:h,static_url:PublisherConfig.external_static_url};
if(b&&Publisher.hasOuterHTML){var l=b.outerHTML,g='<div id="'+i+'">',m="</div>";l=l.substring(g.length,l.length-m.length);
l=l.replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");for(var d in e){var j=new RegExp("{"+d+"}","g");
l=l.replace(j,e[d]);}$("publish_output").set("html",l);if(c!=="plain"){hljs.highlightBlock($("publish_output"));
}}else{$("publish_output").set("text",e.image_url);}};function onFileSelected(a){$("publish_field_overlay_src").value=a;
Publisher.onChange();}function onInit(){GenericPopup.initButtons();Publisher.init();}window.addEvent("domready",onInit);
