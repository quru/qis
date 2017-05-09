/*!
 * image-defer.js
 * 
 * A simple dependency-free JavaScript library for implementing deferred (lazy)
 * image loading on a web page.
 * 
 * Source code:   https://github.com/quru/image-defer/
 * Date started:  24 Apr 2017
 * By:            Matt Fozard
 * Copyright:     Quru Ltd (www.quru.com)
 * Licence:
 * 
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published
 * by the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 * 
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see http://www.gnu.org/licenses/
 */

"use strict";

var ImageDefer = ImageDefer || {};

(function (options) {

    this.version = '0.2';

    // Public options - apply or set defaults (define ImageDefer.options externally to apply them here)
    this.options = {
        maxLoaded: options.maxLoaded || 100,
        onImageRequested: options.onImageRequested || null,
        onImageLoaded: options.onImageLoaded || null,
        onImageUnloaded: options.onImageUnloaded || null,
        scrollingStopMillis: options.scrollingStopMillis || 500,
        scrollingSkipRate: options.scrollingSkipRate || 0.8
    };

    // Private internal state
    var _state = {
        imagesLoaded: 0,
        images: [],
        maxBucket: 0,
        scrolling: false,
        resizing: false,
        scrollInfo: {
            last:    { pos: 0, time: 0 },
            current: { pos: 0, time: 0 }
        },
        scrollChecker: null,
        resizeChecker: null,
        lastVisibleBuckets: {
            start: -1,
            end: -1
        }
    };

    // Private image state flags
    var _imgState = {
        unloaded: 0,
        loading: 1,
        loaded: 2,
        unloading: 3
    };

    // Runs a delayed function so as to not hold up the browser
    this.requestCallBack = function(callbackFn) {
        if (window.requestAnimationFrame) requestAnimationFrame(callbackFn);
        else setTimeout(callbackFn, 20);
    }.bind(this);

    // Loads the currently visible images
    this.lazyLoadImages = function() {
        var vpPos = this.viewportPos(),
            visibleBuckets = this.getBuckets(vpPos.top, vpPos.height),
            bucket;

        // Pause loading while the viewport is resizing
        if (_state.resizing)
            return;

        if ((visibleBuckets.start !== _state.lastVisibleBuckets.start) ||
            (visibleBuckets.end !== _state.lastVisibleBuckets.end)) {

            // Load all images in the visible buckets, if they're not already loading
            // console.log('Lazily loading images for buckets ' + visibleBuckets.start + ' to ' + visibleBuckets.end);
            for (bucket = visibleBuckets.start; bucket <= visibleBuckets.end; bucket++) {
                if (_state.images[bucket]) {
                    _state.images[bucket].forEach(function(img) {
                        this.loadImage(img);
                    }.bind(this));
                }
            }

            // Don't repeat the same buckets next time around (consecutive scroll events)
            _state.lastVisibleBuckets.start = visibleBuckets.start;
            _state.lastVisibleBuckets.end = visibleBuckets.end;
        }
    }.bind(this);

    // Unloads hidden images if the max loaded limit has been reached
    this.trimImages = function() {
        if (_state.imagesLoaded > this.options.maxLoaded) {
            var vpPos = this.viewportPos(),
                visibleBuckets = this.getBuckets(vpPos.top, vpPos.height),
                unloadRequests = 0,
                unloadTotal = (_state.imagesLoaded - this.options.maxLoaded),
                self = this,
                bucket;

            var imageVisible = function(img) {
                for (var vb = visibleBuckets.start; vb <= visibleBuckets.end; vb++) {
                    if (_state.images[vb] && _state.images[vb].indexOf(img) !== -1)
                        return true;
                }
                return false;
            };
            var unloadFn = function(bucket) {
                var unloaded = 0;
                // If the bucket exists (has images in it) and is not visible
                if (_state.images[bucket] && (bucket < visibleBuckets.start || bucket > visibleBuckets.end)) {
                    _state.images[bucket].forEach(function(img) {
                        // img is in a hidden bucket, but it could span buckets, so before
                        // unloading we need to make sure that it isn't also in a visible bucket
                        if (!imageVisible(img)) {
                            if (self.unloadImage(img))
                                unloaded++;
                        }
                    });
                }
                return unloaded;
            };

            // If the user is scrolling down, unload from the top, else vice versa
            if (_state.scrollInfo.current.pos > _state.scrollInfo.last.pos) {
                // console.log('Too many images, unloading from the top');
                for (bucket = 0; (bucket <= _state.maxBucket) && (unloadRequests < unloadTotal); bucket++) {
                    unloadRequests += unloadFn(bucket);
                }
            }
            else {
                // console.log('Too many images, unloading from the bottom');
                for (bucket = _state.maxBucket; (bucket >= 0) && (unloadRequests < unloadTotal); bucket--) {
                    unloadRequests += unloadFn(bucket);
                }
            }
        }
    }.bind(this);

    // Loads the deferred-src for a single image (no effect if already loaded)
    this.loadImage = function(img) {
        if (!img._defer_state) {
            // console.log('Requesting image ' + img._defer_final_src);
            if (!img._defer_load_event) {
                img._defer_load_event = function() { this.onImageLoad(img); }.bind(this);
                img.addEventListener('load', img._defer_load_event);
            }
            img._defer_state = _imgState.loading;
            img.setAttribute('src', img._defer_final_src);
            _state.imagesLoaded++;
            // Was the image loaded immediately from browser cache?
            if (img.complete) {
                // Did the load event fire? If not (browsers vary on this), run it manually
                if (!img._defer_state)
                    this.onImageLoad(img);
            }
            else {
                // Trigger the image requested event
                if (this.options.onImageRequested)
                    this.options.onImageRequested.call(this, img);
            }
            return true;
        }
        return false;
    }.bind(this);

    // Loads the original/placeholder src for a single image (no effect if already unloaded)
    this.unloadImage = function(img) {
        if (img._defer_state && (img._defer_state !== _imgState.unloading)) {
            // console.log('Resetting image back to ' + img._defer_initial_src);
            img._defer_state = _imgState.unloading;
            img.setAttribute('src', img._defer_initial_src);
            _state.imagesLoaded--;
            // Was the image loaded immediately from browser cache?
            if (img.complete) {
                // Did the load event fire? If not (browsers vary on this), run it manually
                if (img._defer_state)
                    this.onImageLoad(img);
            }
            return true;
        }
        return false;
    }.bind(this);

    // Handler for when a requested image src is loaded
    this.onImageLoad = function(img) {
        // Firefox intermittently generates duplicate load events, 1 with complete as
        // false and 1 with complete as true. Possibly related to caching behaviour?
        if (!img.complete)
            return;
        // Even with that, we still intermittently get duplicate events, so everything
        // that follows needs to be aware that it might get called twice.

        if (this.urlsMatch(img.src, img._defer_final_src)) {
            // Image lazy load is complete
            img._defer_state = _imgState.loaded;
            if (this.options.onImageLoaded)
                this.options.onImageLoaded.call(this, img);
            // Later - check and handle the image limit
            this.requestCallBack(this.trimImages);
        }
        else if (this.urlsMatch(img.src, img._defer_initial_src)) {
            // Image unloaded is complete (it reloaded its placeholder src)
            img._defer_state = _imgState.unloaded;
            if (this.options.onImageUnloaded)
                this.options.onImageUnloaded.call(this, img);
        }
    }.bind(this);

    // Handler for scroll events
    this.onScroll = function() {
        // Discard more than 1 event per ms (also avoids div by 0 below)
        var timeNow = Date.now();
        if (_state.scrolling && (_state.scrollInfo.current.time === timeNow))
            return;

        // Track scrolling
        _state.scrolling = true;
        _state.scrollInfo.last.pos = _state.scrollInfo.current.pos;    // Avoid object creation during
        _state.scrollInfo.last.time = _state.scrollInfo.current.time;  // repeated rapid scroll events
        _state.scrollInfo.current.pos = this.viewportPos().top;
        _state.scrollInfo.current.time = timeNow;
        // Later - detect when scrolling stops
        if (!_state.scrollChecker) {
            _state.scrollChecker = setTimeout(
                this.peekScroll,
                this.options.scrollingStopMillis
            );
        }
        // Load images on the fly if scrolling is slow enough
        var scrollRate = Math.abs((_state.scrollInfo.current.pos - _state.scrollInfo.last.pos) / (_state.scrollInfo.current.time - _state.scrollInfo.last.time));
        // console.log('Scrolled to ' + _state.scrollInfo.current.pos + ', rate ' + scrollRate + ' px/ms');
        if (scrollRate < this.options.scrollingSkipRate) {
            this.requestCallBack(this.lazyLoadImages);
        }
    }.bind(this);

    // Handler for viewport resize events
    this.onResize = function() {
        _state.resizing = true;
        // When the page layout has finished changing we need to re-compute
        // all the buckets and load any newly visible images
        if (_state.resizeChecker) {
            clearTimeout(_state.resizeChecker);
        }
        _state.resizeChecker = setTimeout(function() {
            // console.log('The viewport has been resized');
            _state.resizing = false;
            _state.resizeChecker = null;
            this.reset();
        }.bind(this), 500);
    }.bind(this);

    // Detection for when scrolling has stopped
    this.peekScroll = function() {
        var timeNow = Date.now(),
            scrollInfo = _state.scrollInfo.current;

        if ((timeNow - scrollInfo.time >= this.options.scrollingStopMillis * 0.9) &&
            (this.viewportPos().top === scrollInfo.pos)) {
            // Scrolling has stopped
            _state.scrolling = false;
            _state.scrollChecker = null;
            // console.log('Scrolling stopped, images currently loaded ' + _state.imagesLoaded);
            this.requestCallBack(this.lazyLoadImages);
            if (_state.imagesLoaded > this.options.maxLoaded)
                this.requestCallBack(this.trimImages);
        }
        else {
            // Check again in a while
            _state.scrollChecker = setTimeout(
                this.peekScroll,
                this.options.scrollingStopMillis
            );
        }
    }.bind(this);

    // To speed things up, images are indexed by their vertical location
    // This returns a zero-based numeric index value (bucket number) for a given location and height
    // which can be multiple buckets if the object spans bucket boundaries and/or multiple buckets
    this.getBuckets = function(top, height) {
        var bucketSize = 200;
        return {
            start: Math.floor(top / bucketSize),
            end: Math.floor((top + height) / bucketSize)
        };
    };

    // Returns the vertical scroll position and height of the browser's visual viewport
    this.viewportPos = function() {
        return {
            top: window.pageYOffset || document.documentElement.scrollTop || 0,
            height: window.innerHeight || document.documentElement.offsetHeight || 0
        };
    };

    // Returns the vertical location and height of a DOM element
    this.elementPos = function(element) {
        var eRect = element.getBoundingClientRect();
        return {
            top: this.viewportPos().top + eRect.top,
            height: eRect.height
        };
    }.bind(this);

    // Returns whether 2 URLs are the same
    this.urlsMatch = function(url1, url2) {
        // The easy case
        if (url1 === url2)
            return true;
        // The case where one URL is relative and one is absolute
        this._aEl1 = this._aEl1 || document.createElement('a');
        this._aEl2 = this._aEl2 || document.createElement('a');
        this._aEl1.href = url1;  // Will be converted to absolute if relative
        this._aEl2.href = url2;  // "
        return this._aEl1.href === this._aEl2.href;
    }.bind(this);

    // Finds and sets up lazy loading for all images in the page, and loads the currently visible images
    // This function needs to be called whenever the page layout (vertical positions) changes
    this.reset = function() {
        // console.log('Resetting image list and state');
        _state.imagesLoaded = 0;
        _state.images = [];
        _state.maxBucket = 0;
        _state.lastVisibleBuckets.start = -1;
        _state.lastVisibleBuckets.end = -1;
        // Set up all images
        var images = document.querySelectorAll('img');
        for (var i = 0; i < images.length; i++) {
            this.addImage(images[i]);
        }
        // Load the images that are visible now
        this.requestCallBack(this.lazyLoadImages);
    }.bind(this);

    // Adds an image to be controlled by image-defer (no effect if the image has no data-defer-src attribute)
    this.addImage = function(element) {
        var deferSrc = element.getAttribute('data-defer-src'),
            initialSrc = element.getAttribute('src'),
            elPos, buckets, bucket;

        if (deferSrc) {
            // Add to the images list
            elPos = this.elementPos(element);
            buckets = this.getBuckets(elPos.top, elPos.height);
            for (bucket = buckets.start; bucket <= buckets.end; bucket++) {
                if (!_state.images[bucket]) {
                    // Initialise a new bucket
                    _state.images[bucket] = [];
                    if (bucket > _state.maxBucket)
                        _state.maxBucket = bucket;
                }
                _state.images[bucket].push(element);
            }
            // Set the deferred state of the image (only once, as reset() may be called repeatedly)
            if (element._defer_state === undefined) {
                element._defer_initial_src = initialSrc;
                element._defer_final_src = deferSrc;
                element._defer_state = this.urlsMatch(initialSrc, deferSrc) ? _imgState.loaded : _imgState.unloaded;
            }
            // Add to loaded image count (if loaded or loading)
            if ((element._defer_state === _imgState.loaded) || (element._defer_state === _imgState.loading))
                _state.imagesLoaded++;
            // console.log('Added image for ' + deferSrc + ' at ' + elPos.top + ', state ' + element._defer_state);
            return true;
        }
        return false;
    }.bind(this);

    // Removes an image from image-defer control, optionally loading it now (applying the data-defer-src attribute)
    this.removeImage = function(element, load) {
        var deferSrc = element._defer_final_src,
            currState = element._defer_state,
            elPos, elIdx, buckets, bucket;

        if (deferSrc) {
            // Remove from the images list
            elPos = this.elementPos(element);
            buckets = this.getBuckets(elPos.top, elPos.height);
            for (bucket = buckets.start; bucket <= buckets.end; bucket++) {
                if (_state.images[bucket]) {
                    elIdx = _state.images[bucket].indexOf(element);
                    if (elIdx !== -1)
                        _state.images[bucket].splice(elIdx, 1);
                }
            }
            // Remove event handlers
            if (element._defer_load_event)
                element.removeEventListener('load', element._defer_load_event);
            // Remove custom attrs
            delete element._defer_load_event;
            delete element._defer_initial_src;
            delete element._defer_final_src;
            delete element._defer_state;
            // Remove from loaded image count (if loaded or loading)
            if ((currState === _imgState.loaded) || (currState === _imgState.loading))
                _state.imagesLoaded--;
            else if (load)  // Load the final src if requested
                element.setAttribute('src', deferSrc);
            // console.log('Removed image for ' + deferSrc + ' at ' + elPos.top + ', state ' + currState);
        }
    }.bind(this);

    // Returns the number of images that are currently loaded and displayed
    this.imagesLoaded = function() {
        return _state.imagesLoaded;
    };

    // Returns whether image-defer functionality is supported by this browser environment
    this.supportedBrowser = function() {
        return !!(document.addEventListener && document.querySelectorAll &&
                  document.documentElement.getBoundingClientRect &&
                  Array.prototype.forEach);
    };

    // Initialises the library for the current web page
    this.init = function() {
        window.addEventListener('resize', this.onResize);
        window.addEventListener('orientationchange', this.onResize);
        document.addEventListener('scroll', this.onScroll);
        this.reset();
    }.bind(this);

}).call(ImageDefer, ImageDefer.options || {});


// Automatically initialise image-defer on page load
if (ImageDefer.supportedBrowser()) {
    if (document.readyState !== 'loading') ImageDefer.init();
    else document.addEventListener('DOMContentLoaded', ImageDefer.init);
}
else if (console && console.warn) {
    console.warn('image-defer: Unsupported browser');
}
