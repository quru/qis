/*!
	Document:      mootools-extras.js
	Date started:  22 Mar 2013
	By:            Matt Fozard
	Purpose:       MooTools additions and customisations
	Requires:      MooTools Core
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
*/
if(is_touch()){var Drag=new Class({Implements:[Events,Options],options:{snap:6,unit:"px",grid:false,style:true,limit:false,handle:false,invert:false,preventDefault:false,stopPropagation:false,compensateScroll:false,modifiers:{x:"left",y:"top"}},initialize:function(){var b=Array.link(arguments,{options:Type.isObject,element:function(c){return c!=null;
}});this.element=document.id(b.element);this.document=this.element.getDocument();this.setOptions(b.options||{});
var a=typeOf(this.options.handle);this.handles=((a=="array"||a=="collection")?$$(this.options.handle):document.id(this.options.handle))||this.element;
this.mouse={now:{},pos:{}};this.value={start:{},now:{}};this.offsetParent=(function(d){var e=d.getOffsetParent();
var c=!e||(/^(?:body|html)$/i).test(e.tagName);return c?window:document.id(e);})(this.element);this.selection="selectstart" in document?"selectstart":"touchstart";
this.compensateScroll={start:{},diff:{},last:{}};if("ondragstart" in document&&!("FileReader" in window)&&!Drag.ondragstartFixed){document.ondragstart=Function.from(false);
Drag.ondragstartFixed=true;}this.bound={start:this.start.bind(this),check:this.check.bind(this),drag:this.drag.bind(this),stop:this.stop.bind(this),cancel:this.cancel.bind(this),eventStop:Function.from(false),scrollListener:this.scrollListener.bind(this)};
this.attach();},attach:function(){this.handles.addEvent("touchstart",this.bound.start);if(this.options.compensateScroll){this.offsetParent.addEvent("scroll",this.bound.scrollListener);
}return this;},detach:function(){this.handles.removeEvent("touchstart",this.bound.start);if(this.options.compensateScroll){this.offsetParent.removeEvent("scroll",this.bound.scrollListener);
}return this;},scrollListener:function(){if(!this.mouse.start){return;}var a=this.offsetParent.getScroll();
if(this.element.getStyle("position")=="absolute"){var b=this.sumValues(a,this.compensateScroll.last,-1);
this.mouse.now=this.sumValues(this.mouse.now,b,1);}else{this.compensateScroll.diff=this.sumValues(a,this.compensateScroll.start,-1);
}if(this.offsetParent!=window){this.compensateScroll.diff=this.sumValues(this.compensateScroll.start,a,-1);
}this.compensateScroll.last=a;this.render(this.options);},sumValues:function(d,c,e){var b={},a=this.options;
for(z in a.modifiers){if(!a.modifiers[z]){continue;}b[z]=d[z]+c[z]*e;}return b;},start:function(a){var k=this.options;
if(a.rightClick){return;}if(k.preventDefault){a.preventDefault();}if(k.stopPropagation){a.stopPropagation();
}this.compensateScroll.start=this.compensateScroll.last=this.offsetParent.getScroll();this.compensateScroll.diff={x:0,y:0};
this.mouse.start=a.page;this.fireEvent("beforeStart",this.element);var d=k.limit;this.limit={x:[],y:[]};
var f,h,b=this.offsetParent==window?null:this.offsetParent;for(f in k.modifiers){if(!k.modifiers[f]){continue;
}var c=this.element.getStyle(k.modifiers[f]);if(c&&!c.match(/px$/)){if(!h){h=this.element.getCoordinates(b);
}c=h[k.modifiers[f]];}if(k.style){this.value.now[f]=(c||0).toInt();}else{this.value.now[f]=this.element[k.modifiers[f]];
}if(k.invert){this.value.now[f]*=-1;}this.mouse.pos[f]=a.page[f]-this.value.now[f];if(d&&d[f]){var e=2;
while(e--){var g=d[f][e];if(g||g===0){this.limit[f][e]=(typeof g=="function")?g():g;}}}}if(typeOf(this.options.grid)=="number"){this.options.grid={x:this.options.grid,y:this.options.grid};
}var j={touchmove:this.bound.check,touchend:this.bound.cancel};j[this.selection]=this.bound.eventStop;
this.document.addEvents(j);},check:function(a){if(this.options.preventDefault){a.preventDefault();}var b=Math.round(Math.sqrt(Math.pow(a.page.x-this.mouse.start.x,2)+Math.pow(a.page.y-this.mouse.start.y,2)));
if(b>this.options.snap){this.cancel();this.document.addEvents({touchmove:this.bound.drag,touchend:this.bound.stop});
this.fireEvent("start",[this.element,a]).fireEvent("snap",this.element);}},drag:function(b){var a=this.options;
if(a.preventDefault){b.preventDefault();}this.mouse.now=this.sumValues(b.page,this.compensateScroll.diff,-1);
this.render(a);this.fireEvent("drag",[this.element,b]);},render:function(a){for(var b in a.modifiers){if(!a.modifiers[b]){continue;
}this.value.now[b]=this.mouse.now[b]-this.mouse.pos[b];if(a.invert){this.value.now[b]*=-1;}if(a.limit&&this.limit[b]){if((this.limit[b][1]||this.limit[b][1]===0)&&(this.value.now[b]>this.limit[b][1])){this.value.now[b]=this.limit[b][1];
}else{if((this.limit[b][0]||this.limit[b][0]===0)&&(this.value.now[b]<this.limit[b][0])){this.value.now[b]=this.limit[b][0];
}}}if(a.grid[b]){this.value.now[b]-=((this.value.now[b]-(this.limit[b][0]||0))%a.grid[b]);}if(a.style){this.element.setStyle(a.modifiers[b],this.value.now[b]+a.unit);
}else{this.element[a.modifiers[b]]=this.value.now[b];}}},cancel:function(a){this.document.removeEvents({touchmove:this.bound.check,touchend:this.bound.cancel});
if(a){this.document.removeEvent(this.selection,this.bound.eventStop);this.fireEvent("cancel",this.element);
}},stop:function(b){var a={touchmove:this.bound.drag,touchend:this.bound.stop};a[this.selection]=this.bound.eventStop;
this.document.removeEvents(a);this.mouse.start=null;if(b){this.fireEvent("complete",[this.element,b]);
}}});Element.implement({makeResizable:function(a){var b=new Drag(this,Object.merge({modifiers:{x:"width",y:"height"}},a));
this.store("resizer",b);return b.addEvent("drag",function(){this.fireEvent("resize",b);}.bind(this));
}});Drag.Move=new Class({Extends:Drag,options:{droppables:[],container:false,precalculate:false,includeMargins:true,checkDroppables:true},initialize:function(b,a){this.parent(b,a);
b=this.element;this.droppables=$$(this.options.droppables);this.setContainer(this.options.container);
if(this.options.style){if(this.options.modifiers.x=="left"&&this.options.modifiers.y=="top"){var c=b.getOffsetParent(),d=b.getStyles("left","top");
if(c&&(d.left=="auto"||d.top=="auto")){b.setPosition(b.getPosition(c));}}if(b.getStyle("position")=="static"){b.setStyle("position","absolute");
}}this.addEvent("start",this.checkDroppables,true);this.overed=null;},setContainer:function(a){this.container=document.id(a);
if(this.container&&typeOf(this.container)!="element"){this.container=document.id(this.container.getDocument().body);
}},start:function(a){if(this.container){this.options.limit=this.calculateLimit();}if(this.options.precalculate){this.positions=this.droppables.map(function(b){return b.getCoordinates();
});}this.parent(a);},calculateLimit:function(){var k=this.element,f=this.container,e=document.id(k.getOffsetParent())||document.body,i=f.getCoordinates(e),d={},c={},l={},h={},n={},b=e.getScroll();
["top","right","bottom","left"].each(function(r){d[r]=k.getStyle("margin-"+r).toInt();c[r]=k.getStyle("border-"+r).toInt();
l[r]=f.getStyle("margin-"+r).toInt();h[r]=f.getStyle("border-"+r).toInt();n[r]=e.getStyle("padding-"+r).toInt();
},this);var g=k.offsetWidth+d.left+d.right,q=k.offsetHeight+d.top+d.bottom,j=0+b.x,m=0+b.y,p=i.right-h.right-g+b.x,a=i.bottom-h.bottom-q+b.y;
if(this.options.includeMargins){j+=d.left;m+=d.top;}else{p+=d.right;a+=d.bottom;}if(k.getStyle("position")=="relative"){var o=k.getCoordinates(e);
o.left-=k.getStyle("left").toInt();o.top-=k.getStyle("top").toInt();j-=o.left;m-=o.top;if(f.getStyle("position")!="relative"){j+=h.left;
m+=h.top;}p+=d.left-o.left;a+=d.top-o.top;if(f!=e){j+=l.left+n.left;if(!n.left&&j<0){j=0;}m+=e==document.body?0:l.top+n.top;
if(!n.top&&m<0){m=0;}}}else{j-=d.left;m-=d.top;if(f!=e){j+=i.left+h.left;m+=i.top+h.top;}}return{x:[j,p],y:[m,a]};
},getDroppableCoordinates:function(c){var b=c.getCoordinates();if(c.getStyle("position")=="fixed"){var a=window.getScroll();
b.left+=a.x;b.right+=a.x;b.top+=a.y;b.bottom+=a.y;}return b;},checkDroppables:function(){var a=this.droppables.filter(function(d,c){d=this.positions?this.positions[c]:this.getDroppableCoordinates(d);
var b=this.mouse.now;return(b.x>d.left&&b.x<d.right&&b.y<d.bottom&&b.y>d.top);},this).getLast();if(this.overed!=a){if(this.overed){this.fireEvent("leave",[this.element,this.overed]);
}if(a){this.fireEvent("enter",[this.element,a]);}this.overed=a;}},drag:function(a){this.parent(a);if(this.options.checkDroppables&&this.droppables.length){this.checkDroppables();
}},stop:function(a){this.checkDroppables();this.fireEvent("drop",[this.element,this.overed,a]);this.overed=null;
return this.parent(a);}});Element.implement({makeDraggable:function(a){var b=new Drag.Move(this,a);this.store("dragger",b);
return b;}});var Sortables=new Class({Implements:[Events,Options],options:{opacity:1,clone:false,revert:false,handle:false,dragOptions:{}},initialize:function(a,b){this.setOptions(b);
this.elements=[];this.lists=[];this.idle=true;this.addLists($$(document.id(a)||a));if(!this.options.clone){this.options.revert=false;
}if(this.options.revert){this.effect=new Fx.Morph(null,Object.merge({duration:250,link:"cancel"},this.options.revert));
}},attach:function(){this.addLists(this.lists);return this;},detach:function(){this.lists=this.removeLists(this.lists);
return this;},addItems:function(){Array.flatten(arguments).each(function(a){this.elements.push(a);var b=a.retrieve("sortables:start",function(c){this.start.call(this,c,a);
}.bind(this));(this.options.handle?a.getElement(this.options.handle)||a:a).addEvent("touchstart",b);},this);
return this;},addLists:function(){Array.flatten(arguments).each(function(a){this.lists.include(a);this.addItems(a.getChildren());
},this);return this;},removeItems:function(){return $$(Array.flatten(arguments).map(function(a){this.elements.erase(a);
var b=a.retrieve("sortables:start");(this.options.handle?a.getElement(this.options.handle)||a:a).removeEvent("touchstart",b);
return a;},this));},removeLists:function(){return $$(Array.flatten(arguments).map(function(a){this.lists.erase(a);
this.removeItems(a.getChildren());return a;},this));},getClone:function(b,a){if(!this.options.clone){return new Element(a.tagName).inject(document.body);
}if(typeOf(this.options.clone)=="function"){return this.options.clone.call(this,b,a,this.list);}var c=a.clone(true).setStyles({margin:0,position:"absolute",visibility:"hidden",width:a.getStyle("width")}).addEvent("touchstart",function(d){a.fireEvent("touchstart",d);
});if(c.get("html").test("radio")){c.getElements("input[type=radio]").each(function(d,e){d.set("name","clone_"+e);
if(d.get("checked")){a.getElements("input[type=radio]")[e].set("checked",true);}});}return c.inject(this.list).setPosition(a.getPosition(a.getOffsetParent()));
},getDroppables:function(){var a=this.list.getChildren().erase(this.clone).erase(this.element);if(!this.options.constrain){a.append(this.lists).erase(this.list);
}return a;},insert:function(c,b){var a="inside";if(this.lists.contains(b)){this.list=b;this.drag.droppables=this.getDroppables();
}else{a=this.element.getAllPrevious().contains(b)?"before":"after";}this.element.inject(b,a);this.fireEvent("sort",[this.element,this.clone]);
},start:function(b,a){if(!this.idle||b.rightClick||["button","input","a","textarea"].contains(b.target.get("tag"))){return;
}this.idle=false;this.element=a;this.opacity=a.getStyle("opacity");this.list=a.getParent();this.clone=this.getClone(b,a);
this.drag=new Drag.Move(this.clone,Object.merge({droppables:this.getDroppables()},this.options.dragOptions)).addEvents({onSnap:function(){b.stop();
this.clone.setStyle("visibility","visible");this.element.setStyle("opacity",this.options.opacity||0);
this.fireEvent("start",[this.element,this.clone]);}.bind(this),onEnter:this.insert.bind(this),onCancel:this.end.bind(this),onComplete:this.end.bind(this)});
this.clone.inject(this.element,"before");this.drag.start(b);},end:function(){this.drag.detach();this.element.setStyle("opacity",this.opacity);
if(this.effect){var b=this.element.getStyles("width","height"),d=this.clone,c=d.computePosition(this.element.getPosition(this.clone.getOffsetParent()));
var a=function(){this.removeEvent("cancel",a);d.destroy();};this.effect.element=d;this.effect.start({top:c.top,left:c.left,width:b.width,height:b.height,opacity:0.25}).addEvent("cancel",a).chain(a);
}else{this.clone.destroy();}this.reset();},reset:function(){this.idle=true;this.fireEvent("complete",this.element);
},serialize:function(){var c=Array.link(arguments,{modifier:Type.isFunction,index:function(d){return d!=null;
}});var b=this.lists.map(function(d){return d.getChildren().map(c.modifier||function(e){return e.get("id");
},this);},this);var a=c.index;if(this.lists.length==1){a=0;}return(a||a===0)&&a>=0&&a<this.lists.length?b[a]:b;
}});}