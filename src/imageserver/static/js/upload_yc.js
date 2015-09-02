/*!
	Document:      upload.js
	Date started:  14 Jun 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server File Upload helpers
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
	22Oct2012  Matt  Converted to use upload JSON API, added HTML5 progress support
	13Jan2015  Matt  Multiple file, drag and drop support
	17Mar2015  Matt  Add folder browse
*/
"use strict";
var Upload={enhancedUpload:false,droppedFiles:null};Upload.init=function(){addEventEx("uploadform","submit",Upload.onSubmit);
addEventEx("path","keyup",Upload.onPathKey);addEventEx("resetfiles","click",Upload.onResetFiles);addEventEx("resetdir","click",Upload.onResetDir);
addEventEx("folder_browse","click",Upload.onFolderBrowse);$("dropzone").ondragover=Upload.onDragOver;
$("dropzone").ondragend=Upload.onDragEnd;$("dropzone").ondrop=Upload.onDragDrop;$("submit").disabled=false;
Upload.enhancedUpload=Upload.isEnhancedUpload();if(!Upload.enhancedUpload){$("dropfiles").setStyle("display","none");
}};Upload.onResetFiles=function(){$("files").value="";};Upload.onResetDir=function(){$("directory").value="";
};Upload.onResetDropzone=function(){$("dropzone").removeClass("active");$("dropzone").set("html","Drop your files here");
Upload.droppedFiles=null;};Upload.onPathKey=function(a){if(a.code!=9){$("path_index_manual").checked=true;
}};Upload.onFolderBrowse=function(){$("path_index_manual").checked=true;popup_iframe($(this).getProperty("data-browse-url"),575,650);
return false;};Upload.onDragOver=function(a){a.stopPropagation();a.preventDefault();$(this).addClass("active");
};Upload.onDragEnd=function(a){a.stopPropagation();a.preventDefault();$(this).removeClass("active");};
Upload.onDragDrop=function(a){a.stopPropagation();a.preventDefault();if(a.dataTransfer&&a.dataTransfer.files&&a.dataTransfer.files.length){Upload.droppedFiles=a.dataTransfer.files;
$("dropzone").set("html",Upload.droppedFiles.length+" file"+(Upload.droppedFiles.length>1?"s":"")+" dropped");
if(validate_isempty("files")&&validate_isempty("directory")){$("selectfiles").addClass("collapse");}}};
Upload.onSubmit=function(a){if(!Upload.validate()){return false;}Upload.setInfo(null);Upload.setError(null);
Upload.setProgress(Upload.enhancedUpload?0:-1);$("submit").value="Please wait...";$("submit").disabled=true;
if(Upload.enhancedUpload){a.stop();Upload.runEnhancedUpload();return false;}else{$("upload_target").removeEvents("load");
$("upload_target").addEvent("load",Upload.onIFrameResponse);return true;}};Upload.validate=function(){form_clearErrors("uploadform");
if(validate_isempty("files")&&validate_isempty("directory")&&!Upload.droppedFiles){form_setError("files");
alert("You must select a file to upload");return false;}if($2("path_index_manual").checked&&validate_isempty("path")){form_setError("path");
alert("You must enter the name of the folder to upload to");return false;}if(Upload.droppedFiles&&!Upload.enhancedUpload){form_setError("files");
alert("Sorry, your browser cannot upload dropped files.\nPlease use the file selector instead.");Upload.onResetDropzone();
return false;}return true;};Upload.onResponse=function(){$("submit").value="Upload complete";Upload.setProgress(100);
};Upload.onIFrameResponse=function(){try{Upload.onResponse();var a=Upload.getIFrameBody($("upload_target"));
if(a){Upload.onJsonResponse(JSON.decode(a.innerText,true));}}catch(b){}};Upload.onJsonResponse=function(j){Upload.onResponse();
var f=j.data,c=[],h=[];for(var a in f){if(f[a]["error"]!==undefined){h.push({filename:a,result:f[a]["error"]});
}else{c.push({filename:a,result:f[a]});}}var k="../uploadcomplete/?nocache="+String.uniqueID();if(j.status==APICodes.SUCCESS){window.location.replace(k);
}else{var l="",e="",b=false;if(c.length>0){var g=(c.length>1)?" images were ":" image was ";l=c.length+g+'uploaded successfully (<a href="'+k+'">view successful uploads</a>).';
e="But the following problems occurred:<br/>";b=true;}else{if(h.length==1){e="Sorry, there was a problem uploading your image:<br/>"+h[0].result.message+"<br/><br/>";
}else{e="Sorry, the following problems occurred uploading your images:<br/>";b=true;}}if(b){e+="<ul>\n";
for(var d=0;d<h.length;d++){e+="<li><code>"+h[d].filename+"</code> : "+h[d].result.message+"</li>\n";
}e+="</ul><br/>\n";}if(l){Upload.setInfo(l);}Upload.setError(e);$("submit").value=" Upload now ";$("submit").disabled=false;
setTimeout(function(){Upload.setProgress(0);},1000);}};Upload.runEnhancedUpload=function(){var b=$("uploadform"),c=new FormData(b),d=new XMLHttpRequest();
if(Upload.droppedFiles){for(var a=0;a<Upload.droppedFiles.length;a++){c.append("files",Upload.droppedFiles[a]);
}}b.api_json_as_text.value="false";d.upload.addEventListener("progress",function(f){Upload.setProgress(f.lengthComputable?Math.round(f.loaded*100/f.total):-1);
},false);d.addEventListener("load",function(){Upload.onJsonResponse(getAPIError(d.status,d.responseText));
},false);d.addEventListener("error",function(){Upload.onJsonResponse(getAPIError(d.status,d.responseText?d.responseText:d.statusText));
},false);d.addEventListener("abort",function(){Upload.onJsonResponse(getAPIError(d.status,"The upload was interrupted"));
},false);d.open(b.method,b.action);d.send(c);};Upload.isEnhancedUpload=function(){var a=XMLHttpRequest?new XMLHttpRequest():null;
return(a&&a.upload&&(FormData!=undefined));};Upload.setProgress=function(a){if($("upload_progress")){try{if(a>=0){$("upload_progress").value=a;
}else{$("upload_progress").removeProperty("value");}}catch(b){}try{if(a>0){$("upload_progress").innerHTML=a+"%";
}else{$("upload_progress").innerHTML="";}}catch(b){}}};Upload.setMsg=function(a,b){if(b){a.setStyle("display","block");
a.set("html",b);}else{a.setStyle("display","none");}};Upload.setInfo=function(a){Upload.setMsg($("info_msg"),a);
};Upload.setError=function(a){Upload.setMsg($("err_msg"),a);};Upload.getIFrameBody=function(b){var c=b.contentDocument||b.contentWindow.document,a=c.getElementsByTagName("body");
return(a.length>0)?$(a[0]):null;};function onFolderSelected(a){if(a==="/"||a==="\\"){a="";}form_clearErrors("uploadform");
$("path").value=a;}window.addEvent("domready",Upload.init);