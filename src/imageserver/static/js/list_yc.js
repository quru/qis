/*!
	Document:      list.js
	Date started:  07 Jul 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server File Browsing helpers
	Requires:      base.js
	               preview_popup.js
	               MooTools Core 1.3 (no compat)
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
	21Sep2011  Matt  Improve popup x position, allow popup to appear under mouse
	                 cursor, prevent hidden popup blocking page elements
	04Apr2012  Matt  Request previews as JPG (fixes previews of PDFs)
	17Jan2013  Matt  Share with folder_list.html
	23Jan2013  Matt  Add folder actions menu handling
	10Feb2015  Matt  Add support for HTTP 202 responses
	06Oct2015  Matt  Refactored image popup JS into preview_popup.js
*/
"use strict";
function onInit(){var b=$$(".preview_popup")[0];if(b){var a=new ImagePopup(b);a.attachToElements(".image_preview");
}GenericPopup.initButtons();$$(".select_folder").each(function(c){c.addEvent("click",function(){onFolderSelectClick(c.getProperty("data-path"));
return false;});});$$(".select_file").each(function(c){c.addEvent("click",function(){onFileSelectClick(c.getProperty("data-path"));
return false;});});addEventEx("folder_create","click",onFolderCreateClick);addEventEx("folder_rename","click",onFolderRenameClick);
addEventEx("folder_move","click",onFolderMoveClick);addEventEx("folder_delete","click",onFolderDeleteClick);
}function onFolderSelectClick(a){if(window.parent&&window.parent.onFolderSelected){window.parent.onFolderSelected(a);
}GenericPopup.closePage();}function onFileSelectClick(a){if(window.parent&&window.parent.onFileSelected){window.parent.onFileSelected(a);
}GenericPopup.closePage();}function validateFolderName(b){var a=$("path_sep").value,c=b.indexOf(".");
if(c==0){alert("The folder name cannot start with '.'");return false;}if((b.indexOf(a)!=-1)||(b.indexOf("..")!=-1)){alert("The folder name cannot contain '"+a+"' or '..'");
return false;}return true;}function onFolderCreateClick(){var d=$("folder_path").value,b=$("path_sep").value;
if((d=="")||(d==b)){var f="Create a new folder called:";}else{var f="Create a new folder in "+d+" called:";
}var a=prompt(f);if(a){a=a.trim();}if(!a){return false;}if(!validateFolderName(a)){setTimeout(onFolderCreateClick,1);
return false;}var e=$("folder_admin_create_url").value,c=join_path(d,a,b);new Request.JSON({url:e,method:"post",data:{path:c},noCache:true,onSuccess:function(h,g){window.location.reload();
},onFailure:function(h){var g=getAPIError(h.status,h.responseText?h.responseText:h.statusText);alert("The folder could not be created.\n\n"+g.message);
}}).send();return false;}function onFolderRenameClick(){var d=$("folder_name").value;var a=prompt("Rename this folder to:",d);
if(a){a=a.trim();}if(!a||(a==d)){return false;}if(!validateFolderName(a)){setTimeout(onFolderRenameClick,1);
return false;}var f=$("folder_admin_url").value,b=$("parent_folder_path").value,c=$("path_sep").value,e=join_path(b,a,c);
updatePathAsync(f,{path:e},true);return false;}function onFolderMoveClick(){popup_iframe($("folder_browse_url").value,575,500);
return false;}function onFolderSelected(a){setTimeout(function(){moveToFolder(a);},100);}function moveToFolder(e){var b=$("folder_name").value;
if(!confirm("Are you sure you want to move "+b+" into "+e+" ?\n\nAll sub-folders and images will also be moved; this may take a long time.")){return;
}var d=$("folder_admin_url").value,a=$("path_sep").value,c=join_path(e,b,a);updatePathAsync(d,{path:c},false);
}function onFolderDeleteClick(){var b=$("folder_path").value;if(!confirm("Are you sure you want to delete "+b+" ?\n\nAll sub-folders and images will also be deleted; this may take a long time.\n\n*** This action cannot be undone! ***")){return false;
}wait_form_open("Please wait while the folder is deleted...");var a=$("folder_admin_url").value;new Request.JSON({url:a,method:"delete",emulation:false,noCache:true,onSuccess:function(e,d){wait_form_close();
if(this.status==APICodes.SUCCESS_TASK_ACCEPTED){alert("This task is taking a long time and will continue in the background.\n\nYou can refresh the page to see when it has completed.");
}var c=$("parent_folder_path").value;changePath(c);},onFailure:function(d){wait_form_close();var c=getAPIError(d.status,d.responseText?d.responseText:d.statusText);
alert("The folder could not be deleted.\n\n"+c.message);}}).send();return false;}function updatePathAsync(c,e,f){var b=f?"renamed":"moved",d="The folder could not be "+b+".",a="Please wait while the folder is "+b+"...";
wait_form_open(a);new Request.JSON({url:c,method:"put",emulation:false,data:e,noCache:true,onSuccess:function(j,i){wait_form_close();
if(this.status==APICodes.SUCCESS_TASK_ACCEPTED){alert("This task is taking a long time and will continue in the background.\n\nYou can refresh the page to see when it has completed.");
var g=$("parent_folder_path").value;}else{var h=j.data,g=encodeURIComponent(h.path);}changePath(g);},onFailure:function(h){wait_form_close();
var g=getAPIError(h.status,h.responseText?h.responseText:h.statusText);alert(d+"\n\n"+g.message);}}).send();
}function changePath(c){var b=window.location.href,e=b.lastIndexOf("path="),a=b.indexOf("&",e),d=b.substring(0,e+5)+c;
if(a!=-1){d+=b.substring(a);}window.location.href=d;}window.addEvent("domready",onInit);