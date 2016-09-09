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
	12Oct2015  Matt  Added HTML5 <picture> and <img srcset> outputs
	31Aug2016  Matt  v2.2 Replaced server defaults with default template
	06Sep2016  Matt  Default fields to template values on template selection
*/
"use strict";
var Publisher={previewImageRC:0,cropImageRC:0,templateSpec:{},templateSpecKV:{},imageSpec:{},previewSpec:{}};
Publisher.init=function(){addEventEx("crop_image","load",Publisher.refreshedCropImage);addEventEx("crop_image","load",function(){Publisher.resetCropping(true);
});addEventEx("preview_image","load",function(){Publisher.refreshedPreview(false);});addEventEx("preview_image","error",function(){Publisher.refreshedPreview(true);
});addEventEx("publish_field_template","change",Publisher.onTemplateChanged);addEventEx("publish_field_page","change",Publisher.onPageChanged);
addEventEx("publish_field_fill","change",Publisher.onFillChanged);addEventEx("publish_field_autofill","change",Publisher.onAutoFillChanged);
addEventEx("publish_field_transfill","change",Publisher.onTransFillChanged);addEventEx("publish_field_flip","change",Publisher.onFlipChanged);
addEventEx("publish_field_rotation","change",Publisher.onRotationChanged);addEventEx("sizing_units","change",function(){Publisher.onUnitsChanged(true);
});addEventEx("overlay_src_browse","click",Publisher.onBrowseOverlay);addEventEx("publish_download","click",Publisher.onPublishDownload);
addEventEx("publish_type","change",Publisher.onPublishTypeChanged);$$("img.help").each(function(a){addEventEx(a,"click",function(){Publisher.toggleHelp(a);
});});$$(".publish_field").each(function(a){addEventEx(a,"change",Publisher.onChange);});Publisher.popupHelp=new IframePopup($$(".preview_popup")[0],true,function(){Publisher.showingHelp=false;
});Publisher.hasOuterHTML=($("publish_output").outerHTML!==undefined);Publisher.initSpecs();Publisher.onUnitsChanged(false);
Publisher.onTemplateChanged();if($("crop_image").complete){Publisher.resetCropping(false);}};Publisher.initSpecs=function(){var c=$("preview_image").getProperty("src"),b=c.indexOf("?"),a=c.substring(b+1).cleanQueryString().replace(/\+/g," ");
Publisher.previewURL=c.substring(0,b);Publisher.previewSpec=a.parseQueryString();Publisher.previewSpec.cache="0";
Publisher.previewSpec.stats="0";Publisher.imageURL=PublisherConfig.external_image_url;Publisher.imageSpec.src=Publisher.previewSpec.src;
};Publisher.onBrowseOverlay=function(){popup_iframe($(this).getProperty("data-browse-url"),575,650);return false;
};Publisher.onTemplateChanged=function(){var a=$("template_fields"),d=$("publish_field_template"),b=d.options[d.selectedIndex].getProperty("data-id"),c=PublisherConfig.template_api_url;
Publisher.templateSpec={};Publisher.templateSpecKV={};a.empty();a.set("text",PublisherText.loading);if(!b){b=PublisherConfig.default_template_id;
}new Request.JSON({url:c.replace("/0/","/"+b+"/"),onSuccess:function(f,e){Publisher.setTemplateInfo(f.data);
},onFailure:function(e){a.set("text",PublisherText.loading_failed);}}).get();};Publisher.onUnitsChanged=function(d){var b=$("publish_field_dpi_x"),f=$("publish_field_width"),h=$("publish_field_height"),a=$("sizing_units"),e=a.options[a.selectedIndex].value,c=parseInt(b.value,10)||PublisherConfig.default_print_dpi,g=false;
if(e=="px"){f.removeProperty("step");h.removeProperty("step");b.removeProperty("placeholder");if(b.value===""+PublisherConfig.default_print_dpi){b.value="";
g=true;}if(f.value){f.value=Publisher.toPx(parseFloat(f.value),this.previousUnits,c)||"";g=true;}if(h.value){h.value=Publisher.toPx(parseFloat(h.value),this.previousUnits,c)||"";
g=true;}}else{f.setProperty("step","0.00001");h.setProperty("step","0.00001");b.setProperty("placeholder",PublisherConfig.default_print_dpi);
if(!b.value){b.value=PublisherConfig.default_print_dpi;g=true;}if(f.value){var i=Publisher.toPx(parseFloat(f.value),this.previousUnits,c);
f.value=Publisher.fromPx(i,e,c)||"";g=true;}if(h.value){var i=Publisher.toPx(parseFloat(h.value),this.previousUnits,c);
h.value=Publisher.fromPx(i,e,c)||"";g=true;}}this.previousUnits=e;if(g&&d){Publisher.onChange();}};Publisher.onPageChanged=function(){if(Publisher.cropSpec){Publisher.cropSpec.page=this.value;
Publisher.refreshCropImage();}};Publisher.onFlipChanged=function(){if(Publisher.cropSpec){Publisher.cropSpec.flip=this.value;
Publisher.refreshCropImage();}};Publisher.onRotationChanged=function(){if(Publisher.cropSpec){Publisher.cropSpec.angle=this.value;
Publisher.refreshCropImage();}};Publisher.onFillChanged=function(){$("publish_field_autofill").checked=false;
$("publish_field_transfill").checked=false;};Publisher.onAutoFillChanged=function(){if(this.checked){$("publish_field_transfill").checked=false;
$("publish_field_fill").value="#ffffff";}};Publisher.onTransFillChanged=function(){if(this.checked){$("publish_field_autofill").checked=false;
$("publish_field_fill").value="#ffffff";}};Publisher.onPublishDownload=function(){var a=this.getProperty("data-url");
if(a){window.location=a;}};Publisher.onPublishTypeChanged=function(){Publisher.refreshPublishOutput();
};Publisher.onChange=function(){$$(".publish_field").each(function(h){if(h.type==="checkbox"){Publisher.imageSpec[h.name]=h.checked?"1":"0";
}else{if(h.selectedIndex!==undefined&&h.options!==undefined){Publisher.imageSpec[h.name]=h.options[h.selectedIndex].value;
}else{Publisher.imageSpec[h.name]=h.value;}}});if(Publisher.imageSpec.transfill==="1"){Publisher.imageSpec.fill="none";
}if(Publisher.imageSpec.autofill==="1"){Publisher.imageSpec.fill="auto";}delete Publisher.imageSpec.transfill;
delete Publisher.imageSpec.autofill;var a=$("sizing_units"),d=a.options[a.selectedIndex].value;if(d!="px"){var g=parseInt(Publisher.imageSpec.dpi,10)||PublisherConfig.default_print_dpi;
if(Publisher.imageSpec.width){Publisher.imageSpec.width=Publisher.toPx(parseFloat(Publisher.imageSpec.width),d,g)||0;
}if(Publisher.imageSpec.height){Publisher.imageSpec.height=Publisher.toPx(parseFloat(Publisher.imageSpec.height),d,g)||0;
}}var f,e,c,b;for(f in Publisher.imageSpec){e=Publisher.webFieldToTemplateKey(f);c=Publisher.imageSpec[f];
b=Publisher.templateSpecKV[e];if(f=="src"||f=="tmp"){continue;}if(typeof c==="string"){c=c.toLowerCase();
}if(typeof b==="string"){b=b.toLowerCase();}if((b==c)||(!b&&!c)||(b===true&&c==="1")||(b===false&&c==="0")||(b==null&&c==="0")||(b==null&&c==="#ffffff")){delete Publisher.imageSpec[f];
}}if(Publisher.imageSpec.tmp===""){delete Publisher.imageSpec.tmp;}if(Publisher.imageSpec.fill&&Publisher.imageSpec.fill.charAt(0)==="#"){Publisher.imageSpec.fill=Publisher.imageSpec.fill.substring(1);
}Publisher.refreshWarnings();Publisher.refreshPreview();Publisher.refreshPublishOutput();};Publisher.reset=function(j,a){if(a===undefined){a={};
}var i=function(l,k){var m=a[l];return((m!==undefined)&&(m!==null)&&(m!=="")&&(m!==0))?m:k;};if(Publisher.showingHelp){Publisher.toggleHelp();
}$$("label").each(function(k){k.removeClass("highlight");});$$("input").each(function(m){var l=Publisher.webFieldToTemplateKey(m.name);
if(m.type==="checkbox"){m.checked=(i(l,false)===true);}else{if(m.type==="color"){var k=i(l,"");m.value=(k&&k!=="auto"&&k!=="none")?k:"#ffffff";
}else{m.value=i(l,"");}}});$$("select").each(function(m){var l=Publisher.webFieldToTemplateKey(m.name);
if(l!=="template"||j){var n=i(l,"");if(typeof n==="string"){n=n.toLowerCase();}for(var k=0;k<m.options.length;
k++){if(m.options[k].value.toLowerCase()==n){m.selectedIndex=k;return;}}m.selectedIndex=0;}});var d=i("fill","");
if(d==="auto"){$("publish_field_autofill").checked=true;}if(d==="none"){$("publish_field_transfill").checked=true;
}if(j){Publisher.templateSpec={};Publisher.templateSpecKV={};$("template_fields").empty();}Publisher.clearWarnings();
Publisher.onUnitsChanged(false);for(var f in a){var c=i(f,null);if(c&&(c!=="#ffffff")){var e=$("publish_field_"+f);
if(e){var b=e.getParent().getFirst("label");if(b){b.addClass("highlight");}}}}var h=Publisher.cropSpec?(Publisher.cropSpec.page+Publisher.cropSpec.flip+Publisher.cropSpec.angle):NaN;
Publisher.resetCropping(false);Publisher.cropSpec.page=$("publish_field_page").value;Publisher.cropSpec.flip=$("publish_field_flip").value;
Publisher.cropSpec.angle=$("publish_field_rotation").value;var g=(Publisher.cropSpec.page+Publisher.cropSpec.flip+Publisher.cropSpec.angle);
if(g!==h){Publisher.refreshCropImage();}Publisher.onChange();};Publisher.webFieldToTemplateKey=function(a){switch(a){case"src":return"filename";
case"tmp":return"template";case"halign":return"align_h";case"valign":return"align_v";case"angle":return"rotation";
case"autocropfit":return"crop_fit";case"autosizefit":return"size_fit";case"overlay":return"overlay_src";
case"ovpos":return"overlay_pos";case"ovsize":return"overlay_size";case"ovopacity":return"overlay_opacity";
case"icc":return"icc_profile";case"intent":return"icc_intent";case"bpc":return"icc_bpc";case"dpi":return"dpi_x";
case"attach":return"attachment";case"expiry":return"expiry_secs";case"stats":return"record_stats";default:return a;
}};Publisher.templateToKV=function(b){var c={};for(var a in b){c[a]=b[a].value;}return c;};Publisher.fromPx=function(d,b,a){var c=d/a;
switch(b){case"px":return d;case"in":return c.toFixed(3);case"mm":return(c/0.0393701).toFixed(3);default:return 0;
}};Publisher.toPx=function(d,b,a){switch(b){case"px":return d;case"in":var c=d;break;case"mm":var c=d*0.0393701;
break;default:var c=0;break;}return Math.round(c*a);};Publisher.setTemplateInfo=function(b){var d=b.template,a=$("template_fields"),f=$("publish_field_template"),c=f.options[f.selectedIndex].getProperty("data-id");
if(!c){c=""+PublisherConfig.default_template_id;}if(b&&(b.id===parseInt(c))){Publisher.templateSpec=d;
Publisher.templateSpecKV=Publisher.templateToKV(d);Publisher.reset(false,Publisher.templateSpecKV);var e=b.id===PublisherConfig.default_template_id;
a.empty();a.set("text",e?PublisherText.default_template_labels:PublisherText.template_labels);a.grab(new Element("br"));
a.grab(new Element("button",{text:PublisherText.reset_changes,style:"margin-top: 0.3em",events:{click:function(){Publisher.reset(false,Publisher.templateSpecKV);
}}}));}};Publisher.refreshPreview=function(){var e=function(f){try{return parseInt(f,10);}catch(s){return 0;
}};var m=function(f){return f&&(f!=="false")&&(f!=="0");};if(++Publisher.previewImageRC>1){return;}var c=["width","height","colorspace","format","attach","xref","stats"];
var i=Publisher.imageSpec,p=Object.clone(Publisher.previewSpec),n=Publisher.templateSpecKV;for(var j in i){if(!c.contains(j)){p[j]=i[j];
}}var h=(i.format||n.format||"").toLowerCase();if(["gif","jpg","jpeg","pjpg","pjpeg","png","svg"].contains(h)){p.format=h;
}var b=e(i.width)||e(n.width)||0,g=e(i.height)||e(n.height)||0,k=(i.autosizefit!==undefined)?m(i.autosizefit):m(n.size_fit),r=(i.autocropfit!==undefined)?m(i.autocropfit):m(n.crop_fit),o=e(p.width),d=e(p.height),l=false;
if(b&&(b<=o)){p.width=b;l=!g||(g<=d);}if(g){if(g<=d){p.height=g;l=!b||(b<=o);}else{l=false;}}if(b&&g){if(!l){var a=b/g;
if(a>=1){p.height=Math.round(o/a);}else{p.width=Math.round(d*a);}}if(!k){delete p.autosizefit;}if(k){delete p.autocropfit;
}}else{if(r){delete p.autocropfit;}}var q=Publisher.previewURL+"?"+Object.toQueryString(p);if($("preview_image").getProperty("src")===q){return Publisher.refreshedPreview();
}$("preview_image").setStyle("display","");$("preview_error").setStyle("display","none");$("preview_mask").setStyle("display","block");
$("preview_image").setProperty("src",q);};Publisher.refreshedPreview=function(a){$("preview_mask").setStyle("display","none");
if(a){$("preview_image").setStyle("display","none");$("preview_error").setStyle("display","block");}Publisher.previewImageRC=Math.max(--Publisher.previewImageRC,0);
if(Publisher.previewImageRC>0){Publisher.previewImageRC=0;Publisher.refreshPreview();}};Publisher.toggleHelp=function(b){if(Publisher.showingHelp){Publisher.popupHelp.hide();
Publisher.showingHelp=false;}else{var c=$(b).getProperty("data-anchor"),a=(PublisherConfig.help_url+"#"+c);
Publisher.popupHelp.showAt(b,a);Publisher.showingHelp=true;}return false;};Publisher.resetCropping=function(b){if(Publisher.crop!==undefined){$("crop_fix_aspect").removeEvent("change",Publisher.changeAspectRatio);
Publisher.crop.destroy();}var d={x:$("crop_image").width,y:$("crop_image").height},c=$("crop_image").getProperty("src"),a=c.indexOf("?"),e=c.substring(a+1).cleanQueryString().replace(/\+/g," ");
Publisher.cropURL=c.substring(0,a);Publisher.cropSpec=e.parseQueryString();Publisher.cropSize=d;Publisher.crop=new Lasso.Crop("crop_image",{ratio:false,preset:Publisher.defaultCropRect(),min:[10,10],handleSize:10,opacity:0.6,color:"#000",border:"../static/images/crop.gif",onResize:Publisher.updateCropFields,onComplete:Publisher.endCrop});
$("crop_fix_aspect").selectedIndex=0;$("crop_fix_aspect").addEvent("change",Publisher.changeAspectRatio);
Publisher.resetCropFields();if(b){Publisher.onChange();}};Publisher.defaultCropRect=function(){if(Publisher.cropSize){var c=Publisher.cropSize,e=Publisher.templateSpecKV.top||0,d=Publisher.templateSpecKV.left||0,a=Publisher.templateSpecKV.bottom||1,b=Publisher.templateSpecKV.right||1;
return[c.x*d,c.y*e,c.x*b,c.y*a];}return[0,0,0,0];};Publisher.changeAspectRatio=function(){var a=this.options[this.selectedIndex].value;
if(!a){Publisher.crop.options.ratio=false;}else{Publisher.crop.options.ratio=a.split(":");}Publisher.crop.resetCoords();
Publisher.crop.setDefault();Publisher.onChange();};Publisher.resetCropFields=function(){var d=Publisher.templateSpecKV.top||0,c=Publisher.templateSpecKV.left||0,a=Publisher.templateSpecKV.bottom||1,b=Publisher.templateSpecKV.right||1;
$("publish_field_left").value=c!==0?Math.roundx(c,5):"";$("publish_field_top").value=d!==0?Math.roundx(d,5):"";
$("publish_field_right").value=b!==1?Math.roundx(b,5):"";$("publish_field_bottom").value=a!==1?Math.roundx(a,5):"";
};Publisher.updateCropFields=function(b){var a=(b.w&&b.h)?Math.roundx(b.w/b.h,5):"&ndash;";$("crop_aspect").set("html",a);
$("publish_field_left").value=b.x>0?Math.roundx(b.x/Publisher.cropSize.x,5):"";$("publish_field_top").value=b.y>0?Math.roundx(b.y/Publisher.cropSize.y,5):"";
$("publish_field_right").value=((b.x+b.w)<Publisher.cropSize.x)?Math.roundx((b.x+b.w)/Publisher.cropSize.x,5):"";
$("publish_field_bottom").value=((b.y+b.h)<Publisher.cropSize.y)?Math.roundx((b.y+b.h)/Publisher.cropSize.y,5):"";
};Publisher.refreshCropImage=function(){if(++Publisher.cropImageRC>1){return;}var a=Publisher.cropURL+"?"+Object.toQueryString(Publisher.cropSpec);
if($("crop_image").getProperty("src")===a){return Publisher.refreshedCropImage();}$("crop_image").setProperty("src",a);
};Publisher.refreshedCropImage=function(){Publisher.cropImageRC=Math.max(--Publisher.cropImageRC,0);if(Publisher.cropImageRC>0){Publisher.cropImageRC=0;
Publisher.refreshCropImage();}};Publisher.endCrop=function(a){if(!a||(!a.x&&!a.y&&!a.w&&!a.h)){Publisher.crop.resetCoords();
Publisher.crop.setDefault();a=Publisher.crop.getRelativeCoords();}Publisher.updateCropFields(a);Publisher.onChange();
};Publisher.clearWarnings=function(){$$(".warning").each(function(a){a.dispose();});};Publisher.addWarning=function(a,b){var c=new Element("div",{"class":"warning"});
c.grab(new Element("img",{src:PublisherConfig.warn_icon_url}));c.grab(new Element("span",{html:b}));a.grab(c);
};Publisher.refreshWarnings=function(){Publisher.clearWarnings();var s="";if(Publisher.imageSpec.src){var q=Publisher.imageSpec.src.split(".");
s=(q.length>1)?q.pop().toLowerCase():"";}var k=Publisher.templateSpec,e=k.format?k.format.value:"",g=(k.strip&&k.strip.value===true)?"1":"0",f=k.width?k.width.value:0,b=k.height?k.height.value:0,p=k.colorspace?k.colorspace.value:"",a=k.fill?k.fill.value:"";
var u=Publisher.imageSpec.format||e||s||"",j=["jpg","jpeg","pjpg","pjpeg"].contains(u),c=["png"].contains(u),h=["gif"].contains(u),r=["tif","tiff"].contains(u);
var l=Publisher.imageSpec.strip||g,m=parseInt(Publisher.imageSpec.width,10)||f,n=parseInt(Publisher.imageSpec.height,10)||b,o=Publisher.imageSpec.colorspace||p,v=Publisher.imageSpec.fill||a;
var i=$("publish_field_icc_profile"),d=i.options[i.selectedIndex].getProperty("data-colorspace");if(PublisherConfig.max_width&&(m>PublisherConfig.max_width)){Publisher.addWarning($("group_width"),PublisherText.warn_size);
}if(PublisherConfig.max_height&&(n>PublisherConfig.max_height)){Publisher.addWarning($("group_height"),PublisherText.warn_size);
}if(Publisher.imageSpec.icc&&!j&&!r){Publisher.addWarning($("group_icc"),PublisherText.warn_icc);}if(o){if(o!=="rgb"&&!j&&!r){Publisher.addWarning($("group_colorspace"),PublisherText.warn_colorspace);
}if(Publisher.imageSpec.icc){if(d!==o){Publisher.addWarning($("group_colorspace"),PublisherText.warn_icc_colorspace);
}}}if(l==="1"||l===true){if(Publisher.imageSpec.icc){Publisher.addWarning($("group_strip"),PublisherText.warn_strip);
}if(d==="cmyk"||o==="cmyk"){Publisher.addWarning($("group_strip"),PublisherText.warn_strip_cmyk);}}if((v==="none"||v==="transparent")&&!c&&!h){Publisher.addWarning($("group_fill"),PublisherText.warn_transparency);
}};Publisher.refreshPublishOutput=function(){var e=Object.clone(Publisher.imageSpec),r=Publisher.previewURL+"?"+Object.toQueryString(e),c=Publisher.imageURL+"?"+Object.toQueryString(e);
function l(i){i=i.replace(/%2F/g,"/");return i.replace(/"/g,"%22").replace(/'/g,"%27");}r=l(r);c=l(c);
var a={},g=[480,800,1200];for(var q=0;q<g.length;q++){var n=g[q];e.height=0;e.width=n;a[n]=Publisher.imageURL+"?"+Object.toQueryString(e);
a[n]=l(a[n]);}$("publish_download").setProperty("data-url",r+"&attach=1");var h=$("publish_type"),m=h.options[h.selectedIndex].value,j="output_template_"+m,d=$(j);
var t={server_url:PublisherConfig.external_server_url,image_url:c,image_url_480:a[480],image_url_800:a[800],image_url_1200:a[1200],static_url:PublisherConfig.external_static_url};
if(d&&Publisher.hasOuterHTML){var s=d.outerHTML,f='<div id="'+j+'">',b="</div>";s=s.substring(f.length,s.length-b.length);
s=s.replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");for(var p in t){var o=new RegExp("{"+p+"}","g");
s=s.replace(o,t[p]);}$("publish_output").set("html",s);if(m!=="plain"){hljs.highlightBlock($("publish_output"));
}}else{$("publish_output").set("text",t.image_url);}};function onFileSelected(a){$("publish_field_overlay_src").value=a;
Publisher.onChange();}window.addEvent("domready",function(){GenericPopup.initButtons();Publisher.init();
});