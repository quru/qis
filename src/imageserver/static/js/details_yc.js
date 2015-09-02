/*!
	Document:      details.js
	Date started:  14 Sep 2011
	By:            Matt Fozard
	Purpose:       Quru Image Server file details helpers
	Requires:      base.js, canvas_view.js
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
	17Jan2013  Matt  Added move, rename, delete actions
	10Jun2013  Matt  Prevent multiple clicks on reset
*/
function onInit(){if($("viewport")){canvas_view_init("viewport",$("image_url").value);
}popup_convert_anchor("edit_attrs",575,340,function(){window.location.reload();});popup_convert_anchor("view_stats",575,650);
addEventEx("file_reset","click",onResetClick);addEventEx("file_rename","click",onRenameClick);addEventEx("file_move","click",onMoveClick);
addEventEx("file_delete","click",onDeleteClick);if(window.init_map){init_map();}}function onResetClick(){(new Element("span",{html:"Please wait...","class":"disabled"})).replaces($("file_reset"));
return true;}function validateFileName(b){var a=$("path_sep").value,c=b.indexOf(".");if((b.length<3)||(c<1)||(c==(b.length-1))){alert("The new filename must be in the format: myimage.xyz");
return false;}if((b.indexOf(a)!=-1)||(b.indexOf("..")!=-1)){alert("The new filename cannot contain '"+a+"' or '..'");
return false;}return true;}function onRenameClick(){var c=$("image_file_name").value;var e=prompt("Rename this image file to:",c);
if(e){e=e.trim();}if(!e||(e==c)){return false;}if(!validateFileName(e)){setTimeout(onRenameClick,1);return false;
}var d=$("image_admin_url").value,f=$("image_folder_path").value,a=$("path_sep").value,b=join_path(f,e,a);
updatePathAsync(d,{path:b},"The file could not be renamed.");return false;}function onDeleteClick(){if(!confirm("Are you sure you want to delete this image?")){return false;
}var a=$("image_admin_url").value;new Request.JSON({url:a,method:"delete",emulation:false,noCache:true,onSuccess:function(c,b){window.location.href=$("folder_url").value;
},onFailure:function(c){var b=getAPIError(c.status,c.responseText?c.responseText:c.statusText);alert("The file could not be deleted.\n\n"+b.message);
}}).send();return false;}function onMoveClick(){popup_iframe($("folder_browse_url").value,575,500);return false;
}function onFolderSelected(a){setTimeout(function(){moveToFolder(a);},100);}function moveToFolder(e){if(!confirm("Are you sure you want to move this image to "+e+" ?")){return;
}var d=$("image_admin_url").value,c=$("image_file_name").value,a=$("path_sep").value,b=join_path(e,c,a);
updatePathAsync(d,{path:b},"The file could not be moved.");}function updatePathAsync(a,c,b){new Request.JSON({url:a,method:"put",emulation:false,data:c,noCache:true,onSuccess:function(g,e){var f=g.data,d=window.location.href;
d=d.substring(0,d.lastIndexOf("src=")+4);window.location.href=d+encodeURIComponent(f.src);},onFailure:function(e){var d=getAPIError(e.status,e.responseText?e.responseText:e.statusText);
alert(b+"\n\n"+d.message);}}).send();}window.addEvent("domready",onInit);