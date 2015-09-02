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

if (is_touch()) {

	/* Fix MooTools Sortables on touch devices.
	 * 
	 * This very crude - a copy of the MooTools More modules:
	 * 
	 *   Drag, Drag.Move, Sortables
	 *   
	 * with search/replaces carried out for:
	 * 
	 *   mousedown --> touchstart
	 *   mouseup   --> touchend
	 *   mousemove --> touchmove
	 * 
	 * Known bug - an item cannot be dragged again after being dropped.
	 */


	/*
	---

	script: Drag.js

	name: Drag

	description: The base Drag Class. Can be used to drag and resize Elements using mouse events.

	license: MIT-style license

	authors:
	  - Valerio Proietti
	  - Tom Occhinno
	  - Jan Kassens

	requires:
	  - Core/Events
	  - Core/Options
	  - Core/Element.Event
	  - Core/Element.Style
	  - Core/Element.Dimensions
	  - MooTools.More

	provides: [Drag]
	...

	*/

	var Drag = new Class({

		Implements: [Events, Options],

		options: {/*
			onBeforeStart: function(thisElement){},
			onStart: function(thisElement, event){},
			onSnap: function(thisElement){},
			onDrag: function(thisElement, event){},
			onCancel: function(thisElement){},
			onComplete: function(thisElement, event){},*/
			snap: 6,
			unit: 'px',
			grid: false,
			style: true,
			limit: false,
			handle: false,
			invert: false,
			preventDefault: false,
			stopPropagation: false,
			compensateScroll: false,
			modifiers: {x: 'left', y: 'top'}
		},

		initialize: function(){
			var params = Array.link(arguments, {
				'options': Type.isObject,
				'element': function(obj){
					return obj != null;
				}
			});

			this.element = document.id(params.element);
			this.document = this.element.getDocument();
			this.setOptions(params.options || {});
			var htype = typeOf(this.options.handle);
			this.handles = ((htype == 'array' || htype == 'collection') ? $$(this.options.handle) : document.id(this.options.handle)) || this.element;
			this.mouse = {'now': {}, 'pos': {}};
			this.value = {'start': {}, 'now': {}};
			this.offsetParent = (function(el){
				var offsetParent = el.getOffsetParent();
				var isBody = !offsetParent || (/^(?:body|html)$/i).test(offsetParent.tagName);
				return isBody ? window : document.id(offsetParent);
			})(this.element);
			this.selection = 'selectstart' in document ? 'selectstart' : 'touchstart';

			this.compensateScroll = {start: {}, diff: {}, last: {}};

			if ('ondragstart' in document && !('FileReader' in window) && !Drag.ondragstartFixed){
				document.ondragstart = Function.from(false);
				Drag.ondragstartFixed = true;
			}

			this.bound = {
				start: this.start.bind(this),
				check: this.check.bind(this),
				drag: this.drag.bind(this),
				stop: this.stop.bind(this),
				cancel: this.cancel.bind(this),
				eventStop: Function.from(false),
				scrollListener: this.scrollListener.bind(this)
			};
			this.attach();
		},

		attach: function(){
			this.handles.addEvent('touchstart', this.bound.start);
			if (this.options.compensateScroll) this.offsetParent.addEvent('scroll', this.bound.scrollListener);
			return this;
		},

		detach: function(){
			this.handles.removeEvent('touchstart', this.bound.start);
			if (this.options.compensateScroll) this.offsetParent.removeEvent('scroll', this.bound.scrollListener);
			return this;
		},

		scrollListener: function(){

			if (!this.mouse.start) return;
			var newScrollValue = this.offsetParent.getScroll();

			if (this.element.getStyle('position') == 'absolute'){
				var scrollDiff = this.sumValues(newScrollValue, this.compensateScroll.last, -1);
				this.mouse.now = this.sumValues(this.mouse.now, scrollDiff, 1);
			} else {
				this.compensateScroll.diff = this.sumValues(newScrollValue, this.compensateScroll.start, -1);
			}
			if (this.offsetParent != window) this.compensateScroll.diff = this.sumValues(this.compensateScroll.start, newScrollValue, -1);
			this.compensateScroll.last = newScrollValue;
			this.render(this.options);
		},

		sumValues: function(alpha, beta, op){
			var sum = {}, options = this.options;
			for (z in options.modifiers){
				if (!options.modifiers[z]) continue;
				sum[z] = alpha[z] + beta[z] * op;
			}
			return sum;
		},

		start: function(event){
			var options = this.options;

			if (event.rightClick) return;

			if (options.preventDefault) event.preventDefault();
			if (options.stopPropagation) event.stopPropagation();
			this.compensateScroll.start = this.compensateScroll.last = this.offsetParent.getScroll();
			this.compensateScroll.diff = {x: 0, y: 0};
			this.mouse.start = event.page;
			this.fireEvent('beforeStart', this.element);

			var limit = options.limit;
			this.limit = {x: [], y: []};

			var z, coordinates, offsetParent = this.offsetParent == window ? null : this.offsetParent;
			for (z in options.modifiers){
				if (!options.modifiers[z]) continue;

				var style = this.element.getStyle(options.modifiers[z]);

				// Some browsers (IE and Opera) don't always return pixels.
				if (style && !style.match(/px$/)){
					if (!coordinates) coordinates = this.element.getCoordinates(offsetParent);
					style = coordinates[options.modifiers[z]];
				}

				if (options.style) this.value.now[z] = (style || 0).toInt();
				else this.value.now[z] = this.element[options.modifiers[z]];

				if (options.invert) this.value.now[z] *= -1;

				this.mouse.pos[z] = event.page[z] - this.value.now[z];

				if (limit && limit[z]){
					var i = 2;
					while (i--){
						var limitZI = limit[z][i];
						if (limitZI || limitZI === 0) this.limit[z][i] = (typeof limitZI == 'function') ? limitZI() : limitZI;
					}
				}
			}

			if (typeOf(this.options.grid) == 'number') this.options.grid = {
				x: this.options.grid,
				y: this.options.grid
			};

			var events = {
				touchmove: this.bound.check,
				touchend: this.bound.cancel
			};
			events[this.selection] = this.bound.eventStop;
			this.document.addEvents(events);
		},

		check: function(event){
			if (this.options.preventDefault) event.preventDefault();
			var distance = Math.round(Math.sqrt(Math.pow(event.page.x - this.mouse.start.x, 2) + Math.pow(event.page.y - this.mouse.start.y, 2)));
			if (distance > this.options.snap){
				this.cancel();
				this.document.addEvents({
					touchmove: this.bound.drag,
					touchend: this.bound.stop
				});
				this.fireEvent('start', [this.element, event]).fireEvent('snap', this.element);
			}
		},

		drag: function(event){
			var options = this.options;
			if (options.preventDefault) event.preventDefault();
			this.mouse.now = this.sumValues(event.page, this.compensateScroll.diff, -1);

			this.render(options);
			this.fireEvent('drag', [this.element, event]);
		},  

		render: function(options){
			for (var z in options.modifiers){
				if (!options.modifiers[z]) continue;
				this.value.now[z] = this.mouse.now[z] - this.mouse.pos[z];

				if (options.invert) this.value.now[z] *= -1;
				if (options.limit && this.limit[z]){
					if ((this.limit[z][1] || this.limit[z][1] === 0) && (this.value.now[z] > this.limit[z][1])){
						this.value.now[z] = this.limit[z][1];
					} else if ((this.limit[z][0] || this.limit[z][0] === 0) && (this.value.now[z] < this.limit[z][0])){
						this.value.now[z] = this.limit[z][0];
					}
				}
				if (options.grid[z]) this.value.now[z] -= ((this.value.now[z] - (this.limit[z][0]||0)) % options.grid[z]);
				if (options.style) this.element.setStyle(options.modifiers[z], this.value.now[z] + options.unit);
				else this.element[options.modifiers[z]] = this.value.now[z];
			}
		},

		cancel: function(event){
			this.document.removeEvents({
				touchmove: this.bound.check,
				touchend: this.bound.cancel
			});
			if (event){
				this.document.removeEvent(this.selection, this.bound.eventStop);
				this.fireEvent('cancel', this.element);
			}
		},

		stop: function(event){
			var events = {
				touchmove: this.bound.drag,
				touchend: this.bound.stop
			};
			events[this.selection] = this.bound.eventStop;
			this.document.removeEvents(events);
			this.mouse.start = null;
			if (event) this.fireEvent('complete', [this.element, event]);
		}

	});

	Element.implement({

		makeResizable: function(options){
			var drag = new Drag(this, Object.merge({
				modifiers: {
					x: 'width',
					y: 'height'
				}
			}, options));

			this.store('resizer', drag);
			return drag.addEvent('drag', function(){
				this.fireEvent('resize', drag);
			}.bind(this));
		}

	});


	/*
	---

	script: Drag.Move.js

	name: Drag.Move

	description: A Drag extension that provides support for the constraining of draggables to containers and droppables.

	license: MIT-style license

	authors:
	  - Valerio Proietti
	  - Tom Occhinno
	  - Jan Kassens
	  - Aaron Newton
	  - Scott Kyle

	requires:
	  - Core/Element.Dimensions
	  - Drag

	provides: [Drag.Move]

	...
	*/

	Drag.Move = new Class({

		Extends: Drag,

		options: {/*
			onEnter: function(thisElement, overed){},
			onLeave: function(thisElement, overed){},
			onDrop: function(thisElement, overed, event){},*/
			droppables: [],
			container: false,
			precalculate: false,
			includeMargins: true,
			checkDroppables: true
		},

		initialize: function(element, options){
			this.parent(element, options);
			element = this.element;

			this.droppables = $$(this.options.droppables);
			this.setContainer(this.options.container);

			if (this.options.style){
				if (this.options.modifiers.x == 'left' && this.options.modifiers.y == 'top'){
					var parent = element.getOffsetParent(),
						styles = element.getStyles('left', 'top');
					if (parent && (styles.left == 'auto' || styles.top == 'auto')){
						element.setPosition(element.getPosition(parent));
					}
				}

				if (element.getStyle('position') == 'static') element.setStyle('position', 'absolute');
			}

			this.addEvent('start', this.checkDroppables, true);
			this.overed = null;
		},
		
		setContainer: function(container) {
			this.container = document.id(container);
			if (this.container && typeOf(this.container) != 'element'){
				this.container = document.id(this.container.getDocument().body);
			}
		},

		start: function(event){
			if (this.container) this.options.limit = this.calculateLimit();

			if (this.options.precalculate){
				this.positions = this.droppables.map(function(el){
					return el.getCoordinates();
				});
			}

			this.parent(event);
		},

		calculateLimit: function(){
			var element = this.element,
				container = this.container,

				offsetParent = document.id(element.getOffsetParent()) || document.body,
				containerCoordinates = container.getCoordinates(offsetParent),
				elementMargin = {},
				elementBorder = {},
				containerMargin = {},
				containerBorder = {},
				offsetParentPadding = {},
				offsetScroll = offsetParent.getScroll();

			['top', 'right', 'bottom', 'left'].each(function(pad){
				elementMargin[pad] = element.getStyle('margin-' + pad).toInt();
				elementBorder[pad] = element.getStyle('border-' + pad).toInt();
				containerMargin[pad] = container.getStyle('margin-' + pad).toInt();
				containerBorder[pad] = container.getStyle('border-' + pad).toInt();
				offsetParentPadding[pad] = offsetParent.getStyle('padding-' + pad).toInt();
			}, this);

			var width = element.offsetWidth + elementMargin.left + elementMargin.right,
				height = element.offsetHeight + elementMargin.top + elementMargin.bottom,
				left = 0 + offsetScroll.x,
				top = 0 + offsetScroll.y,
				right = containerCoordinates.right - containerBorder.right - width + offsetScroll.x,
				bottom = containerCoordinates.bottom - containerBorder.bottom - height + offsetScroll.y;

			if (this.options.includeMargins){
				left += elementMargin.left;
				top += elementMargin.top;
			} else {
				right += elementMargin.right;
				bottom += elementMargin.bottom;
			}

			if (element.getStyle('position') == 'relative'){
				var coords = element.getCoordinates(offsetParent);
				coords.left -= element.getStyle('left').toInt();
				coords.top -= element.getStyle('top').toInt();

				left -= coords.left;
				top -= coords.top;
				if (container.getStyle('position') != 'relative'){
					left += containerBorder.left;
					top += containerBorder.top;
				}
				right += elementMargin.left - coords.left;
				bottom += elementMargin.top - coords.top;

				if (container != offsetParent){
					left += containerMargin.left + offsetParentPadding.left;
					if (!offsetParentPadding.left && left < 0) left = 0;
					top += offsetParent == document.body ? 0 : containerMargin.top + offsetParentPadding.top;
					if (!offsetParentPadding.top && top < 0) top = 0;
				}
			} else {
				left -= elementMargin.left;
				top -= elementMargin.top;
				if (container != offsetParent){
					left += containerCoordinates.left + containerBorder.left;
					top += containerCoordinates.top + containerBorder.top;
				}
			}

			return {
				x: [left, right],
				y: [top, bottom]
			};
		},

		getDroppableCoordinates: function(element){
			var position = element.getCoordinates();
			if (element.getStyle('position') == 'fixed'){
				var scroll = window.getScroll();
				position.left += scroll.x;
				position.right += scroll.x;
				position.top += scroll.y;
				position.bottom += scroll.y;
			}
			return position;
		},

		checkDroppables: function(){
			var overed = this.droppables.filter(function(el, i){
				el = this.positions ? this.positions[i] : this.getDroppableCoordinates(el);
				var now = this.mouse.now;
				return (now.x > el.left && now.x < el.right && now.y < el.bottom && now.y > el.top);
			}, this).getLast();

			if (this.overed != overed){
				if (this.overed) this.fireEvent('leave', [this.element, this.overed]);
				if (overed) this.fireEvent('enter', [this.element, overed]);
				this.overed = overed;
			}
		},

		drag: function(event){
			this.parent(event);
			if (this.options.checkDroppables && this.droppables.length) this.checkDroppables();
		},

		stop: function(event){
			this.checkDroppables();
			this.fireEvent('drop', [this.element, this.overed, event]);
			this.overed = null;
			return this.parent(event);
		}

	});

	Element.implement({

		makeDraggable: function(options){
			var drag = new Drag.Move(this, options);
			this.store('dragger', drag);
			return drag;
		}

	});


	/*
	---

	script: Sortables.js

	name: Sortables

	description: Class for creating a drag and drop sorting interface for lists of items.

	license: MIT-style license

	authors:
	  - Tom Occhino

	requires:
	  - Core/Fx.Morph
	  - Drag.Move

	provides: [Sortables]

	...
	*/

	var Sortables = new Class({

		Implements: [Events, Options],

		options: {/*
			onSort: function(element, clone){},
			onStart: function(element, clone){},
			onComplete: function(element){},*/
			opacity: 1,
			clone: false,
			revert: false,
			handle: false,
			dragOptions: {}
		},

		initialize: function(lists, options){
			this.setOptions(options);

			this.elements = [];
			this.lists = [];
			this.idle = true;

			this.addLists($$(document.id(lists) || lists));

			if (!this.options.clone) this.options.revert = false;
			if (this.options.revert) this.effect = new Fx.Morph(null, Object.merge({
				duration: 250,
				link: 'cancel'
			}, this.options.revert));
		},

		attach: function(){
			this.addLists(this.lists);
			return this;
		},

		detach: function(){
			this.lists = this.removeLists(this.lists);
			return this;
		},

		addItems: function(){
			Array.flatten(arguments).each(function(element){
				this.elements.push(element);
				var start = element.retrieve('sortables:start', function(event){
					this.start.call(this, event, element);
				}.bind(this));
				(this.options.handle ? element.getElement(this.options.handle) || element : element).addEvent('touchstart', start);
			}, this);
			return this;
		},

		addLists: function(){
			Array.flatten(arguments).each(function(list){
				this.lists.include(list);
				this.addItems(list.getChildren());
			}, this);
			return this;
		},

		removeItems: function(){
			return $$(Array.flatten(arguments).map(function(element){
				this.elements.erase(element);
				var start = element.retrieve('sortables:start');
				(this.options.handle ? element.getElement(this.options.handle) || element : element).removeEvent('touchstart', start);

				return element;
			}, this));
		},

		removeLists: function(){
			return $$(Array.flatten(arguments).map(function(list){
				this.lists.erase(list);
				this.removeItems(list.getChildren());

				return list;
			}, this));
		},

		getClone: function(event, element){
			if (!this.options.clone) return new Element(element.tagName).inject(document.body);
			if (typeOf(this.options.clone) == 'function') return this.options.clone.call(this, event, element, this.list);
			var clone = element.clone(true).setStyles({
				margin: 0,
				position: 'absolute',
				visibility: 'hidden',
				width: element.getStyle('width')
			}).addEvent('touchstart', function(event){
				element.fireEvent('touchstart', event);
			});
			//prevent the duplicated radio inputs from unchecking the real one
			if (clone.get('html').test('radio')){
				clone.getElements('input[type=radio]').each(function(input, i){
					input.set('name', 'clone_' + i);
					if (input.get('checked')) element.getElements('input[type=radio]')[i].set('checked', true);
				});
			}

			return clone.inject(this.list).setPosition(element.getPosition(element.getOffsetParent()));
		},

		getDroppables: function(){
			var droppables = this.list.getChildren().erase(this.clone).erase(this.element);
			if (!this.options.constrain) droppables.append(this.lists).erase(this.list);
			return droppables;
		},

		insert: function(dragging, element){
			var where = 'inside';
			if (this.lists.contains(element)){
				this.list = element;
				this.drag.droppables = this.getDroppables();
			} else {
				where = this.element.getAllPrevious().contains(element) ? 'before' : 'after';
			}
			this.element.inject(element, where);
			this.fireEvent('sort', [this.element, this.clone]);
		},

		start: function(event, element){
			if (
				!this.idle ||
				event.rightClick ||
				['button', 'input', 'a', 'textarea'].contains(event.target.get('tag'))
			) return;

			this.idle = false;
			this.element = element;
			this.opacity = element.getStyle('opacity');
			this.list = element.getParent();
			this.clone = this.getClone(event, element);

			this.drag = new Drag.Move(this.clone, Object.merge({
				
				droppables: this.getDroppables()
			}, this.options.dragOptions)).addEvents({
				onSnap: function(){
					event.stop();
					this.clone.setStyle('visibility', 'visible');
					this.element.setStyle('opacity', this.options.opacity || 0);
					this.fireEvent('start', [this.element, this.clone]);
				}.bind(this),
				onEnter: this.insert.bind(this),
				onCancel: this.end.bind(this),
				onComplete: this.end.bind(this)
			});

			this.clone.inject(this.element, 'before');
			this.drag.start(event);
		},

		end: function(){
			this.drag.detach();
			this.element.setStyle('opacity', this.opacity);
			if (this.effect){
				var dim = this.element.getStyles('width', 'height'),
					clone = this.clone,
					pos = clone.computePosition(this.element.getPosition(this.clone.getOffsetParent()));

				var destroy = function(){
					this.removeEvent('cancel', destroy);
					clone.destroy();
				};

				this.effect.element = clone;
				this.effect.start({
					top: pos.top,
					left: pos.left,
					width: dim.width,
					height: dim.height,
					opacity: 0.25
				}).addEvent('cancel', destroy).chain(destroy);
			} else {
				this.clone.destroy();
			}
			this.reset();
		},

		reset: function(){
			this.idle = true;
			this.fireEvent('complete', this.element);
		},

		serialize: function(){
			var params = Array.link(arguments, {
				modifier: Type.isFunction,
				index: function(obj){
					return obj != null;
				}
			});
			var serial = this.lists.map(function(list){
				return list.getChildren().map(params.modifier || function(element){
					return element.get('id');
				}, this);
			}, this);

			var index = params.index;
			if (this.lists.length == 1) index = 0;
			return (index || index === 0) && index >= 0 && index < this.lists.length ? serial[index] : serial;
		}

	});

} // if is_touch
