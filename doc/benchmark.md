# Benchmarking

**TL;DR** Skip to the _conclusions_ section below.

QIS comes with a Python script you can use for load testing your image server
and to fine tune the settings. It performs a number of "normal" HTTP requests,
in parallel to simulate multiple clients. The requests include:

* Image thumbnail generation
* Image cropping
* PDF to image thumbnails (if supported)
* Original image downloads
* Zooming image viewer API calls

The script - `src/imageserver/scripts/bench.py` - has no dependencies other
than Python 3.4 or above, so you can copy it to wherever you want to run the
test from.

## Setup

The script requests images from the `test_images` folder on the server, so this
needs to be restored if it has been removed. In the folder permissions, you need
to enable _View and download_ permission for the `test_images` folder and the
`Public` group.

To suppress HTTP 503 errors and allow the test script to clear cached images
as it goes, add the `BENCHMARKING` setting to your `local_settings.py` file.
Remember to remove it when you have finished:

	BENCHMARKING = True

You also need to clear the server's image cache before each test run, by
restarting the Memcached service:

	$ sudo systemctl restart memcached

## Running the script

The best results are obtained by running `bench.py` from a separate machine (or
multiple machines for a large number of simultaneous clients), connected to the
image server with a fast local network. If this is not possible, the next best
thing is to run `bench.py` on the image server itself. This prevents network effects
from spoiling the result, but does not give a true test because the overhead of
running `bench.py` itself reduces the processing power available to QIS. For
real-world testing rather than benchmarking, run `bench.py` from several remote
machines across the internet.

Run the script without any parameters to see the available options:

	$ python3 bench.py
	
	Runs a benchmarking test against an image server by requesting a series
	of sample image URLs. The test can be tuned by adjusting the number of
	image requests, the number of simultaneous requests, and the percentage of
	requests to return from cache. Repeating the test with the same parameters
	will generate the same set of requests so that timings can be compared.

	Usage:
		python bench.py [options] server_url [num_requests] [cache_percent] [num_clients]

	Where:
		server_url is e.g. http://images.example.com/
		num_requests is the number of server requests to make, default 1000
		cache_percent is the percentage of images to return from cache, default 90
		num_clients is the number of simultaneous requests to make, default 4

	Options:
		--verbose to output more detailed status logs
		--only-warm to only warm the cache then skip the actual tests
		--skip-warm to skip the cache warming and run the tests immediately
		--no-pdf to not perform tests of PDF to image conversion

	Examples:
		python bench.py http://images.example.com/
		python bench.py --verbose http://images.example.com/ 5000 80 10

	Notes:
	Set cache_percent to 0 to re-generate every image every time. This is very
	CPU intensive on the image server and tests performance under load. Set
	cache_percent to 100 to serve every image from cache where possible*. This
	tests the level of throughput under ideal conditions. The default value of
	90 represents a typical workload.

	* The tests also include some URLs that are never returned from cache.

To test the best possible server performance, request 100% of images to come
from the server's cache:

	$ python3 bench.py http://images.example.com/ 15000 100 8
	LOG   9986 - Checking connectivity to http://images.example.com/
	LOG   9986 - Building request list
	LOG   9986 - Pre-warming the image cache
	LOG   9986 - Creating clients, running tests
	LOG   9986 - Complete
	
	Results
	=======
	15000 successful requests, 0 errors.
	Run time 16.630899 seconds = 901.935611 requests/sec.
	
	Average response 0.008663 seconds
	  * 1463 non-cached, average response 0.012020 seconds, worst 0.088293 seconds
	  * 13537 from cache, average response 0.008300 seconds, worst 0.077525 seconds

Here 15000 requests were split between 8 simultaneous clients. The average response
time of 0.008 seconds and slowest response below 0.1 seconds indicate that the server
comfortably handled this load. Some responses did not come from cache because the
API calls and original image downloads are not currently cached on the server side.

To test a more realistic workload, request 80 to 90% of images to come from
the server's cache:

	$ python3 bench.py http://images.example.com/ 15000 80 8
	LOG   10093 - Checking connectivity to http://images.example.com/
	LOG   10093 - Building request list
	LOG   10093 - Pre-warming the image cache
	LOG   10093 - Creating clients, running tests
	LOG   10093 - Complete
	
	Results
	=======
	15000 successful requests, 0 errors.
	Run time 307.028436 seconds = 48.855410 requests/sec.
	
	Average response 0.161251 seconds
	  * 3239 non-cached, average response 0.272146 seconds, worst 3.599948 seconds
	  * 11761 from cache, average response 0.130711 seconds, worst 4.711322 seconds

The same test at 80% cache level caused 3239 - 1463 = 1776 new images to be generated
on-the-fly, and represents a fairly heavy workload. The average response time of
0.16 seconds is likely still acceptable, but some clients waited nearly 5 seconds,
indicating that the server struggled with this load in places.

You can find out what percentage of images are coming from cache on your own
server from the _system statistics_ reports menu in QIS.

## Example benchmark results

### Low powered server

A 2 CPU core Intel Celeron @ 2.6GHz, 2GB RAM,
running Red Hat Enterprise Linux 6.5, Apache, Postgres, and Memcached.

	|    mod_wsgi    |   bench.py   | requests/  | worst response |
	| proc * threads |    params    |  second    |    seconds     |
	|----------------|--------------|------------|----------------|
	|      2 * 15    | 1000 100 2   |        304 |            < 1 |
	|      2 * 15    | 1000 100 4   |        336 |                |
	|      4 * 15    | 1000 100 2   |        338 |                |
	|      4 * 15    | 1000 100 4   |        366 |                |
	|                |              |            |                |
	|      1 * 15    | 1000 80 2    |       10.5 |            3.2 |
	|      1 * 15    | 1000 80 4    |       10.0 |            5.2 |
	|      1 * 15    | 1000 80 10   |       13.0 |           10.8 |
	|      2 * 15    | 1000 80 2    |       11.3 |            2.4 |
	|      2 * 15    | 1000 80 4    |       10.8 |            3.6 |
	|      2 * 15    | 1000 80 10   |       14.1 |            9.5 |
	|      4 * 15    | 1000 80 2    |       10.7 |            3.1 |
	|      4 * 15    | 1000 80 4    |       11.9 |            5.0 |
	|      4 * 15    | 1000 80 10   |       14.2 |           10.9 |

Tested with the prefork and worker MPMs in Apache, with no consistent
difference in terms of memory usage, throughput or worst response time.

With all images cached, the highest throughput is with 4 mod_wsgi processes.
When some images are being generated, and discarding results where the worst
case responses are above 10s, the highest throughput and lowest worst cases
are with 2 mod_wsgi processes.

### High powered server

A 10 CPU core Intel Xeon @ 2.9Ghz, way more RAM than is required here,
running Red Hat Enterprise Linux 6.5, Apache, Postgres, and Memcached.

	|    mod_wsgi    |    bench.py   | requests/  | worst response |
	| proc * threads |     params    |  second    |    seconds     |
	|----------------|---------------|------------|----------------|
	|      5 * 15    | 20000 100 10  |        864 |            < 1 |
	|      5 * 15    | 20000 100 20  |       1018 |                |
	|      5 * 15    | 20000 100 50  |       1310 |                |
	|      5 * 15    | 20000 100 100 |       1418 |                |
	|      7 * 15    | 20000 100 10  |        973 |                |
	|      7 * 15    | 20000 100 20  |       1140 |                |
	|      7 * 15    | 20000 100 50  |       1509 |                |
	|      7 * 15    | 20000 100 100 |       1872 |                |
	|     10 * 15    | 20000 100 10  |       1067 |                |
	|     10 * 15    | 20000 100 20  |       1279 |                |
	|     10 * 15    | 20000 100 50  |       1660 |                |
	|     10 * 15    | 20000 100 100 |       2133 |                |
	|                |               |            |                |
	|      5 * 15    | 20000 80 10   |         49 |            3.3 |
	|      5 * 15    | 20000 80 20   |         59 |            5.2 |
	|      5 * 15    | 20000 80 50   |         89 |            8.7 |
	|      5 * 15    | 20000 80 100  |        145 |           15.0 |
	|      7 * 15    | 20000 80 10   |         51 |            4.6 |
	|      7 * 15    | 20000 80 20   |         66 |            4.0 |
	|      7 * 15    | 20000 80 50   |         91 |            5.6 |
	|      7 * 15    | 20000 80 100  |        145 |           16.0 |
	|     10 * 15    | 20000 80 10   |         53 |            5.0 |
	|     10 * 15    | 20000 80 20   |         70 |            9.0 |
	|     10 * 15    | 20000 80 50   |         93 |            6.9 |
	|     10 * 15    | 20000 80 100  |        125 |           16.5 |

Tested with the prefork and worker MPMs in Apache, with no consistent
difference in terms of memory usage, throughput or worst response time.

These numbers paint a clearer picture than the 2 CPU server of how performance
varies with traffic levels and the number of Python workers configured.

With all images cached, more is better once again; but the limits of the server
soon become apparent as soon as images are being generated. At the 80% cache
level we can discard the tests with 100 clients because they all give unacceptable
worst cases of above 10 seconds. Note though that when the server is overloaded,
throughput is better for 5 and 7 mod_wsgi processes (145 requests/s) than for 10
(125 requests/s). With 50 clients, the throughput is nearly the same for 5, 7,
and 10 mod_wsgi processes, but the lowest worst case is for 7.

## Conclusions

It is better to have too few mod_wsgi processes/threads than too many, to avoid
overwhelming the server when many images need to be generated simultaneously.
If you _always_ have a high percentage of images coming from the server's cache,
the number of mod_wsgi workers can be larger. The guidelines given in the tuning
guide seem to work well in the general case, namely that after reserving one CPU
core for each major application on the server, you can define 1 mod_wsgi process
per remaining CPU core. Or on a 1 or 2 core server, do not define more than 1 or
2 mod_wsgi processes.

Apart from benchmarking your Apache/mod_wsgi capacity, you can also use `bench.py`
alongside the tuning guide, to see if for a given server load there is any effect
when changing the other application settings.

---

## Appendix - Development benchmarks

Running the benchmark against QIS's development server is of limited value,
but it does help to identify any major performance improvements or regressions
when developing new features.

As of Flask v1.0 (in QIS v4.0 onwards) the development server is capable of
handling simultaneous client requests where previously it was single-threaded.
It is recommended to run these tests with only a single client (setting
`num_clients` to 1) so that the timings reflect a sum of linear operations,
a more predictable and consistent value than timing parallel operations.
However it is now also possible to test with multiple clients, if you
specifically want to test the handling of parallel requests.

Machine and software versions:

* 2012 MacBook Pro 2.9 GHz Intel Core i7, 16 GB 1600 MHz DDR3
* Python 3.5.4
* ImageMagick 6.8.8-10 Q16 x86_64
* Memcached 1.4.34
* PostgreSQL 9.5.2
* QIS v4.0.0

Setup:

* Enable _View and download_ permission for the `test_images` folder and the `Public` group
* Add to your `conf/local_settings.py` file, the line: `BENCHMARKING = True`
* Restart the Memcached service
* Run the development server with debug mode disabled:  
  `$ export FLASK_ENV=production`  
  `$ make runserver`

### Standard Edition (Pillow library), default settings

Default test:

	$ python3 src/imageserver/scripts/bench.py --no-pdf http://127.0.0.1:5000/ 1000 90 1
	LOG   81858 - Checking connectivity to http://127.0.0.1:5000/
	LOG   81858 - Building request list
	LOG   81858 - Pre-warming the image cache
	LOG   81858 - Creating clients, running tests
	LOG   81858 - Complete

	Results
	=======
	1000 successful requests, 0 errors.
	Run time 99.734788 seconds = 10.026592 requests/sec.

	Average response 0.099538 seconds
	* 195 non-cached responses
		* Average app time 0.491758 seconds
		* Average response 0.493961 seconds
		* Worst response 1.880010 seconds
	* 805 cached responses
		* Average app time 0.001899 seconds
		* Average response 0.003994 seconds
		* Worst response 0.008710 seconds

100% cached test (fastest scenario):

	$ python3 src/imageserver/scripts/bench.py --no-pdf http://127.0.0.1:5000/ 1000 100 1
	LOG   81942 - Checking connectivity to http://127.0.0.1:5000/
	LOG   81942 - Building request list
	LOG   81942 - Pre-warming the image cache
	LOG   81942 - Creating clients, running tests
	LOG   81942 - Complete

	Results
	=======
	1000 successful requests, 0 errors.
	Run time 4.453783 seconds = 224.528225 requests/sec.

	Average response 0.004289 seconds
	* 98 non-cached responses
		* Average app time 0.003090 seconds
		* Average response 0.005231 seconds
		* Worst response 0.009317 seconds
	* 902 cached responses
		* Average app time 0.002013 seconds
		* Average response 0.004186 seconds
		* Worst response 0.006511 seconds

Heavy processing test (slowest scenario):

	$ python3 src/imageserver/scripts/bench.py --no-pdf http://127.0.0.1:5000/ 100 0 1
	LOG   81985 - Checking connectivity to http://127.0.0.1:5000/
	LOG   81985 - Building request list
	LOG   81985 - NOTE! You need to manually clear your image cache if you have previously run these tests.
	LOG   81985 - Creating clients, running tests
	LOG   81985 - Complete

	Results
	=======
	100 successful requests, 0 errors.
	Run time 80.693159 seconds = 1.239262 requests/sec.

	Average response 0.806010 seconds
	* 100 non-cached responses
		* Average app time 0.803680 seconds
		* Average response 0.806010 seconds
		* Worst response 1.770991 seconds
	* 0 from cache

### Premium Edition (ImageMagick library), default settings

Default test:

	$ python3 src/imageserver/scripts/bench.py http://127.0.0.1:5000/ 1000 90 1
	LOG   81471 - Checking connectivity to http://127.0.0.1:5000/
	LOG   81471 - Checking PDF conversion support
	LOG   81471 - Building request list
	LOG   81471 - Pre-warming the image cache
	LOG   81471 - Creating clients, running tests
	LOG   81471 - Complete

	Results
	=======
	1000 successful requests, 0 errors.
	Run time 54.857844 seconds = 18.228934 requests/sec.

	Average response 0.054686 seconds
	* 195 non-cached responses
		* Average app time 0.260914 seconds
		* Average response 0.263169 seconds
		* Worst response 1.308715 seconds
	* 805 cached responses
		* Average app time 0.001979 seconds
		* Average response 0.004185 seconds
		* Worst response 0.012576 seconds

100% cached test (fastest scenario):

	$ python3 src/imageserver/scripts/bench.py http://127.0.0.1:5000/ 1000 100 1
	LOG   81616 - Checking connectivity to http://127.0.0.1:5000/
	LOG   81616 - Checking PDF conversion support
	LOG   81616 - Building request list
	LOG   81616 - Pre-warming the image cache
	LOG   81616 - Creating clients, running tests
	LOG   81616 - Complete

	Results
	=======
	1000 successful requests, 0 errors.
	Run time 4.655934 seconds = 214.779672 requests/sec.

	Average response 0.004488 seconds
	* 98 non-cached responses
		* Average app time 0.003133 seconds
		* Average response 0.005388 seconds
		* Worst response 0.009511 seconds
	* 902 cached responses
		* Average app time 0.002094 seconds
		* Average response 0.004390 seconds
		* Worst response 0.007552 seconds

Heavy processing test (slowest scenario):

	$ python3 src/imageserver/scripts/bench.py http://127.0.0.1:5000/ 100 0 1
	LOG   81717 - Checking connectivity to http://127.0.0.1:5000/
	LOG   81717 - Checking PDF conversion support
	LOG   81717 - Building request list
	LOG   81717 - NOTE! You need to manually clear your image cache if you have previously run these tests.
	LOG   81717 - Creating clients, running tests
	LOG   81717 - Complete

	Results
	=======
	100 successful requests, 0 errors.
	Run time 38.963857 seconds = 2.566481 requests/sec.

	Average response 0.388679 seconds
	* 100 non-cached responses
		* Average app time 0.386199 seconds
		* Average response 0.388679 seconds
		* Worst response 0.962977 seconds
	* 0 from cache
