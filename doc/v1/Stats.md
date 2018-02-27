QIS v1.19 Stats revamp
======================

Current status: complete

System stats and image stats counter fields to be made consistent:

* requests = total number of image requests regardless of response and stats param
* views = total number of images returned
* cached_views = total number of images returned from server cache
* downloads = total number of originals served
* total_bytes = total size of image data responses (not including HTTP headers)
* request_seconds = total time taken generating responses

We will now have 5 types of image response:

* HTTP 200 generated image - increment requests + views + total_bytes + request_seconds
* HTTP 200 image returned from cache - increment requests + views + cached_views + total_bytes + request_seconds
* HTTP 304 not modified - increment requests + request_seconds

plus

* HTTP 200 download original - increment requests + downloads + total_bytes + request_seconds
* HTTP 304 original not modified - increment requests + request_seconds

When the stats=0 image parameter is present:

* System stats will be updated as usual
* Image stats will increment the total requests field only
