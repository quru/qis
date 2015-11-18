# Tuning the QIS installation

The install guide contains enough information to get you going (hopefully!),
but if you want to ensure your image server is being fully utilised, this guide
goes into more detail.

## mod_wsgi

I'm not going to repeat the mod_wsgi documentation. It's fairly well written and
comprehensive, so if you want to know more, go over to
[modwsgi.org](http://www.modwsgi.org/) and have a read.

QIS uses the "daemon mode" of mod_wsgi as it offers several advantages, including
easier configuration and higher performance out of the box.

Tuning the server capacity in daemon mode is a simple case of choosing how many
mod_wsgi processes you want to have running, and how many threads you want each
process to handle. One mod_wsgi thread can service one web request (but see below
for how this relates to the Apache workers). The size of this "worker pool" is
fixed, with the limit being determined by how your Python code uses the CPU or
allocates RAM.

mod_wsgi's daemon mode threads are Python threads rather than native threads.
Python threads are notoriously poor at performing, therefore you should not
configure a high number of threads per process (keep it below 20), and if you
require more workers, increase the number of processes instead.

As a guide to the number of mod_wsgi processes, allocate no more than the
number of CPU cores in your server, minus 1 if Memcached runs on the same server,
minus 1 if Postgres runs on the same server. So for example, on a 4 core CPU
running all the software, set 2 mod_wsgi processes. On an 8 core CPU running
all the software, set 4 to 6 mod_wsgi processes. Choose the lower number if your
server frequently has to generate new images, or the higher number if most of
your images (90% or more) are served from cache. See the _QIS system reports_
section for how to find out the percentage of images coming from cache.

Configure the number of mod_wsgi processes + threads in `/etc/httpd/conf.d/qis.conf`
and `qis-ssl.conf`. The actual conf file location varies by operating system
(e.g. `/etc/apache2`, `/etc/httpd/sites-enabled/`, etc).

## Apache - choice of MPM

The mod_wsgi documentation recommends using the worker MPM, but we have seen no
problems using the prefork MPM (which is the default on most platforms). In fact
when testing a normal QIS workload, prefork and worker perform almost identically.
The worker MPM uses a little less memory, because it creates 1 thread per worker
instead of 1 process per worker.

How to set or change the Apache MPM varies by operating system.
You can see which MPM is currently enabled by running `apachectl -l` or
`httpd -V`.

## Apache - disabling unused modules

Many Apache installations have a large number of Apache modules enabled by default.
Disabling the unused modules does not give any measurable speed improvement, but
does achieve a small memory saving under the prefork MPM. To keep things simple,
it is recommended to leave the default modules and settings in place.

If you do wish to remove the unused modules, look for the `LoadModule` directives
in the main Apache `conf` file. In Red Hat / CentOS 6.x, you can comment out these
modules:

	authn_alias_module, authn_anon_module, authn_dbm_module, authn_default_module,
	authz_owner_module, authz_dbm_module, authz_default_module, ldap_module,
	authnz_ldap_module, include_module, env_module, ext_filter_module,
	mime_magic_module, usertrack_module, dav_module, status_module,
	autoindex_module, info_module, dav_fs_module, vhost_alias_module,
	actions_module, speling_module, userdir_module, substitute_module,
	proxy_balancer_module, proxy_ftp_module, proxy_http_module, proxy_ajp_module,
	proxy_connect_module, cache_module, suexec_module, disk_cache_module,
	cgi_module, version_module

From the same `conf` file you will then also need to remove the standard settings
that depend on those modules:

* `IndexOptions`
* `AddIcon*`
* `DefaultIcon`
* `ReadmeName`
* `HeaderName`
* `IndexIgnore`

This list is based on Hayden James' article
[Strip Down Apache to Improve Performance & Memory Efficiency](http://haydenjames.io/strip-apache-improve-performance-memory-efficiency/).

## Apache - MPM tuning

See mod_wsgi daemon mode settings vs Apache tuning settings below for how many
Apache workers you will need once your mod_wsgi configuration is done. The MPM
tuning settings are then typically in Apache's main `http.conf` file.

For the prefork MPM tuning settings, read:

* [Apache 2.4](http://httpd.apache.org/docs/current/mod/prefork.html)
* [Apache 2.2](http://httpd.apache.org/docs/2.2/mod/prefork.html)

For the worker MPM tuning settings, read:

* [Apache 2.4](http://httpd.apache.org/docs/current/mod/worker.html)
* [Apache 2.2](http://httpd.apache.org/docs/2.2/mod/worker.html)

Then go back and read the tuning settings again. Particularly in Apache 2.2 there
are various rules, guidelines, and dependencies between the settings.

The "correct" values for MPM tuning depends on the types of image QIS will be
serving (small+fast or large+slow) and the traffic levels of your server. You can
watch Graham Dumpleton's PyCon talks (links below) for some interesting insights
on the effects of these settings, and also what not to do.

Note: these configuration settings are different between Apache 2.2 and 2.4. Also
be aware that the same configuration values have different meanings for different
MPMs.

## Apache - KeepAlive

Enabling keep-alive means that an Apache worker will hold open the connection to
a client for a number of seconds, in the expectation that they will make further
requests. If they do, this leads to increased performance for the client via the
re-use of an established "pipeline". If they don't, the Apache worker is needlessly
tied up in an idling state until the keep-alive timeout occurs.

In QIS, a web page typically has multiple images, therefore we usually enable
keep-alive in the expectation of receiving multiple requests from each client.
The timeout value is set low (3 seconds by default) to try and avoid capacity
problems due to tied-up Apache workers.

If your web server is reaching the `MaxClients` limit in Apache while not being
maxed-out, disabling keep-alive will likely allow you to serve more traffic.

## Apache - access logs

The standard QIS configuration enables access logs for QIS traffic. You can disable
these if you wish in the `qis.conf` and `qis-ssl.conf` Apache configuration files.

With access logs enabled, be sure to configure _logrotate_ to prevent the logs
growing in size to unreasonable levels. A busy web site can generate a 1GB access
log in just 1 day. See the [install guide](install.md) for how to do this.

## mod_wsgi tuning settings vs Apache tuning settings

In `http.conf` we can set Apache's `ServerLimit`, `MaxClients`, etc. In `qis.conf`
we can set the mod_wsgi `WSGIDaemonProcess` number of processes and threads.

But for a given number of WSGI connections, what should the Apache settings be?
Does changing one conf file have some effect on the other? If we configure our
expected load for mod_wsgi, do the Apache settings even matter?

Despite the generally excellent mod_wsgi documentation, there is very little
information to be found in terms of how these two tuning sections affect each
other. After many hours of searching, the answer is that they are separate but
related configurations. Increasing the number of Apache workers does not increase
the capacity of mod_wsgi or vice versa. However the 2 areas are related, and do
need to be tuned together.

In mod_wsgi's recommended daemon mode, the Apache workers are serving 2 purposes:

* Serving non-wsgi static file requests such as robots.txt, icons, Javascript, and CSS
* Acting as proxies to the mod_wsgi daemon process + thread pool

The second point indicates that for each mod_wsgi connection we require at least
one Apache worker to act as a proxy. Adding in the first point, we can see that
Apache must be configured to support at least the total WSGI pool size + the expected
static file traffic, in terms of `MaxClients`.

In fact, Graham Dumpleton suggests an approximate ratio of 4 Apache workers to
1 mod_wsgi connection. As discussed in his PyCon 2013 presentation, this is so that
the WSGI module can return data to one Apache worker straight away, and then switch
to servicing the next waiting Apache worker. The Apache workers then take care of
pushing data to slow networks and waiting for keep-alive clients, without holding
up a valuable mod_wsgi connection. The optimum ratio will actually depend on the
size of each request, the network speed of clients, server bandwidth and keep-alive
settings.

The mod_wsgi daemon mode process + thread pool is of a fixed size and is not affected
by the Apache tuning settings. It should be set to the maximum number of concurrent
Python requests you want to support, without overloading the server. Unlike the number
of Apache workers, this pool size is never increased or decreased as the web traffic
changes.

For further information on Apache tuning with mod_wsgi, see Graham Dumpleton's PyCon talks:

* [http://lanyrd.com/2012/pycon/spcdg/](http://lanyrd.com/2012/pycon/spcdg/)
* [http://lanyrd.com/2013/pycon/scdyzk/](http://lanyrd.com/2013/pycon/scdyzk/)

While the 4:1 ratio came from this forum post:
[https://groups.google.com/d/msg/modwsgi/rufSwTh6PLI/hrHJqRSXJy8J](https://groups.google.com/d/msg/modwsgi/rufSwTh6PLI/hrHJqRSXJy8J)

> The one last comment i will say is that there is no point having the total number
> of daemon mode threads (2*100=200) as you have it, being greater than MaxClients
> in Apache. This is because MaxClients is not even going to allow you to get 200
> concurrent request through to the daemon processes as the Apache child processes
> are operating as proxies and so are limited to what MaxClients is set to.
>
> Even a one to one relationship between MaxClients and daemon processes*threads
> is also wrong, as it constricts your ability to get requests into the daemon
> processes.
>
> The appropriate ratio is a fuzzy figure that really depends on your specific
> application and the host you are running on, but a 4 to 1 ratio might be a better
> starting point.
>
> So if MaxClients is 120, then use processes=6 and threads=5 on the daemon processes.

## ImageMagick - Q8 vs Q16 vs Q32

ImageMagick by default is compiled in "Q16" mode, which means use 16 bits per
quantum (pixel RGBA component) resolution during imaging operations. If your server
is a low spec you can instead compile it as Q8, performance will improve and memory
consumption will be approximately halved, at the expense of some image and colour
accuracy.

According to [http://www.imagemagick.org/discourse-server/viewtopic.php?f=2&t=22932](http://www.imagemagick.org/discourse-server/viewtopic.php?f=2&t=22932):

> We recommend Q16. It is a nice balance between performance, memory consumption,
> and mathematical precision. Q8 uses less memory and improves performance.
> Certain image formats require HDRI. You probably don't need a Q32 release.
> The other three cover pretty much all use cases.

If you wish to trade off some image precision in return for the performance
gains of Q8, you'll need to compile ImageMagick from source as described at
[http://www.imagemagick.org/script/advanced-unix-installation.php](http://www.imagemagick.org/script/advanced-unix-installation.php).
Run configure with:

	$ ./configure --with-quantum-depth 8 <your-other-options>

## QIS settings

The following settings, which you can override in your `local_settings.py` file,
may have an impact on the performance and capacity of your server:

* `IMAGE_RESIZE_QUALITY` - setting a value of `1` or `2` will speed up resizing
  operations and reduce the CPU load on your server
* `AUTO_PYRAMID_THRESHOLD` - you can disable this feature by setting a value of
  `0` to prevent (possibly unnecessary) extra image resizing
* `IMAGE_FORMAT_DEFAULT` and `IMAGE_QUALITY_DEFAULT` - some image formats
  are faster to generate than others, lowering the quality (for `jpg` images)
  will reduce the generated image sizes
* `IMAGE_STRIP_DEFAULT` - if you do not generally require embedded colour
  profiles and meta-data e.g. the camera make and model, setting this to `True`
  can reduce the generated image sizes
* `IMAGE_EXPIRY_TIME_DEFAULT` - if your images do not change once uploaded,
  increase this value to 30 days or 1 year so that they are kept for longer
  in client-side web browser caches
* `PDF_BURST_TO_PNG` - you can disable this feature by setting a value of
  `False` to prevent the (possibly unnecessary) automatic creation of images
  from PDF files

## An example

This real life example is a server with 10 CPU cores and 56GB of RAM, running
Red Hat Enterprise Linux 6.5. It is sat behind a proxy server that handles
HTTPS connections, so that almost all the traffic arrives as plain HTTP requests.

### Memory allocation

We will aim for the following allocation of RAM:

1 GB for operating system and miscellaneous processes  
2 GB for Postgres shared cache and client processes  
4 GB for mod_wsgi processes (9 x 0.5GB)  
45 GB for Memcached  
4 GB reserved for occasional large imaging operations, but used by the operating
system when "free" for disk caches and buffers (this is useful for QIS, but
actually expected by Postgres)  
Total 56GB

We need to leave enough RAM free to prevent the o/s swapping. It is particularly
important that the Memcached database fits entirely into RAM!

Note: some swap space may still be used under normal conditions - see the
_checking memory use_ section below.

### mod_wsgi config

Since the mod_wsgi/http/python processes (incorporating ImageMagick) are the most
CPU intensive, allocate at least 1 CPU core per mod_wsgi process. Leaving aside 3
CPU cores for the operating system, Memcached, and Postgres, this leaves 7 then for
mod_wsgi. It is a quirk of this server that the SSL processes receive very little
traffic, not enough to consider here.

	Apache conf	        WSGIDaemonProcess
	                processes        threads
	qis.conf            7              15
	qis-ssl.conf        2              10

All HTTP traffic then is served by (7 x 15) + (2 x 10) = 125 mod_wsgi threads.

As mentioned above, most SSL traffic for this server is actually served through a
proxy server (routed as plain http requests) therefore `qis-ssl.conf` is configured
to provide only 20 threads for a small amount of direct SSL traffic.

### Apache config

Red Hat ships Apache with the prefork MPM (Multi-Processing Module) by default,
and we haven't changed this. In tests, the worker MPM uses the same amount of
memory and gives on average the same performance.

This server powers a web site that uses lots of images, therefore we shall leave
keep-alive enabled, but set it to a fairly short value so that Apache does not hold
idle client connections open for long. If you see "max clients reached" in the Apache
`error_log`, you can either increase the number of Apache workers or disable keep-alive.

In `qis.conf` and `qis-ssl.conf`:

	# KeepAlive: Whether or not to allow persistent connections (more than
	# one request per connection). Set to "Off" to deactivate.
	KeepAlive On
	
	# KeepAliveTimeout: Number of seconds to wait for the next request from the
	# same client on the same connection.
	KeepAliveTimeout 3

Above we configured about 125 mod_wsgi threads. Using the 4:1 ratio guideline for
Apache Workers:mod_wsgi connections then we want around 125 * 4 = 500 Apache workers.
The prefork MPM settings in `httpd.conf` are therefore set to:

	# prefork MPM
	<IfModule prefork.c>
	StartServers       50
	MinSpareServers    25
	MaxSpareServers    75
	ServerLimit        500
	MaxClients         500
	MaxRequestsPerChild  10000
	</IfModule>

This is a busy server, so we immediately launch 50 workers on startup, and then
keep between 25 to 75 workers spare. Note that `StartServers` should always be
between `MinSpareServers` and `MaxSpareServers`, otherwise Apache will immediately
start more (or shut down some) workers before it has even had a chance to analyse
the traffic levels.

### QIS

The standard/base QIS settings allocate 5 database connections[1] per mod_wsgi
process to a database connection pool[2]. The QIS system reports for this server
show that 90% of image requests are served from cache without using the database.
Therefore a pool of 5 connections per process should suffice even though we have
set mod_wsgi to serve 15 threads per process.

[1] In QIS v1.x there are 2 databases - cache control and image management - so
    at 5 connections each this actually defines a pool of up to 10 database
    connections per process.

[2] In fact the software provides an "overflow" which QIS restricts to 1 extra
    connection (per pool, per process), but as we don't expect to use the overflow
    this has not been counted. The Postgres settings below will allow small overflows
    to occur however.

Leaving the standard settings in place then, with 7 mod_wsgi processes for HTTP
and 2 for HTTPS, we will be asking Postgres for up to 9 x 10 = 90 connections.
On top of this we will need a few additional connections for QIS's background tasks.

Postgres (or any database server) can only serve so many connections simultaneously
anyway, especially simultaneous writes. So as long as database activity does not take
up the entire request time and connections are released quickly, then (up to a point)
there is no harm in having a connection pool size much lower than the expected number
of concurrent site users. The pooling software will take care of waiting for a
connection to become free if none are available. In QIS, the database activity time is
typically a small part of the whole request time, so the pool can usually be expected
to contain free connections.

### Postgres

So, aiming roughly for a total memory usage of 2GB, `postgresql.conf` can be tuned
as follows:

	Setting                      Value   Why
	max_connections              120     As described above, we are allowing for 100 connections plus an overflow
	shared_buffers               2GB     Primary working memory, the default value is only 32MB.
	                                     Lower than the "recommended" value as we are reserving much of the server for Memcached and mod_wsgi
	max_fsm_pages                4000000 A value provided by `vacuum -verbose` for the `imagestats` table (not required in Postgres 8.4+)
	wal_buffers                  16MB    Recommended value for our shared_buffers setting (and the default on Postgres 8.4+)
	checkpoint_segments          16      Reasonable value for our settings
	checkpoint_completion_target 0.9     As recommended in the Postgres documentation when checkpoint_segments has been adjusted
	effective_cache_size         4GB     Lower than the "recommended" value as we are reserving much of the server for Memcached and mod_wsgi
	default_statistics_target    100     Recommended value (and the default on Postgres 8.4+)

See also [the Postgres tuning documentation](http://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server)
and consider looking at the `pgtune` utility.

### Memcached

The standard Memcached settings seem to be reasonable, so just set the memory
limit in `/etc/sysconfig/memcached`:

	CACHESIZE="45000"

This server takes approximately 2 days to fill the cache to its maximum size.
When full, the 45 GB limit looks like:

	$ ps -u memcached euf
	USER   PID  %CPU %MEM VSZ      RSS      TTY STAT START   TIME COMMAND
	496    6204 1.0  75.7 46597100 43679944 ?   Ssl  Apr24 105:51 memcached -d -p 11211 -u memcached -m 45000 -c 1024 -P /var/run/memcached/memcached.pid

### Checking memory use

If you're not familiar with Linux memory management, first read the article
[Linux Memory Management - Low on Memory](http://linux-mm.org/Low_On_Memory),
otherwise you might see `MemTotal: 56GB, MemFree: 0.4GB` and think that you're
out of memory when you're not.

Check the size of your Memcached process to see whether the cache has reached its
limit. If it's not yet full, bear in mind the extra memory that is going to be used.

Get a brief overview of memory use with free:

	$ free -m
	             total       used       free     shared    buffers     cached
	Mem:         56348      55736        611          0        188       9898
	-/+ buffers/cache:      45648      10699
	Swap:         8015       2810       5205

Here the server is showing that it is using 45.6GB out of 56GB, which is broadly
in line with the numbers we aimed for. There is 10.7GB of "free" memory, but the
server is putting 10.1GB of that to good use by using it for buffers and filesystem
caching, leaving only 0.6GB genuinely free at that point in time.

For more memory detail, run:

	$ cat /proc/meminfo

But what about the 2.8GB of swap file being used?
We can check whether the server is swapping with:

	$ vmstat -S m 5
	procs -----------memory---------- ---swap-- -----io---- --system-- -----cpu-----
	 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
	 1  0   2947    779    189  10160    0    0   658    37    3    7 21  8 69  2  0
	 6  0   2947    844    189  10184    0    0  4669   110 14335 5579 18  6 73  3  0
	...
	14  0   2946    585    192  10357    0    0  2830   190 12287 3295 13  2 83  2  0
	 2  0   2946    595    192  10363    0    0  2037   935 3861 2727  6  3 88  3  0
	 3  0   2946    661    192  10365    0    0   357    34 3324 2621  3  1 95  0  0

The swap in (si) and swap out (so) values are consistently 0MB, so the server is
not swapping. The operating system has just shifted some rarely accessed items out
of RAM to make room for more useful things.

### System resource limits

If the QIS processes keep closing and the QIS and Apache error logs contain messages
like these:

* `Resource temporarily unavailable`
* `Error code 11 (EAGAIN)`
* `Unable to create thread`
* `Unable to fork`

then you are hitting the operating system's default limits for the number of
processes and threads that can run at once. See the [install guide](install.md)
for how to raise these limits.

## Real world testing and analysis

### QIS system reports

QIS records a number of statistics that you can use to monitor server performance.
To see these, log in and go to Reports, System statistics.

* Total image requests - gives you a view on the number of images being requested,
  and how it varies through the day. This value does not include other types of
  request e.g. Javascript and CSS files. For these, see the Apache access logs.
* Number of images served - this is the number of images actually sent back to
  clients. For web traffic, this is usually less than _total image requests_
  because of client-side web browser caching. If the client already has an
  up-to-date copy of the image, the server can quickly respond with a short
  `HTTP 304 Not modified` message.
* Percentage of images served from cache - for good performance this value should
  be high, 90% or more.
* Slowest response times - if your image processing normally completes in a
  predictably fast time, you can use this metric to see when clients are
  experiencing poor response times.
* CPU usage - if your average CPU usage goes above 50%, response times will begin
  to suffer. Over 80% and you need to take action to increase the size of the cache,
  increase the number of CPUs, decrease the number of mod_wsgi processes/threads,
  or see if you can make better image requests (e.g. reduce the number of
  variations produced for each image).
* RAM usage - this must be kept below 100%, a guideline is to aim for 80 to 90%.
  If too high or too low you can adjust the Memcached cache size, or review the
  memory usage of the other software components.
* Image cache usage - due to the way Memcached works internally, it is normal for
  this value to never go above 90%. If it stays below 80%, your image cache has
  room to spare. You can either leave it for future use, or reduce the Memcached
  cache size and allocate the unused RAM to something else.

### Apache access logs

The Apache access log records all requests made to your server, including dynamic
images, web pages, Javascript, CSS files, and static images. QIS by default logs
to:

* `/var/log/httpd/qis_access_log`
* `/var/log/httpd/qis_ssl_access_log`

with each entry appearing as follows:

	80.219.81.177 [29/May/2015:16:31:21 -0100] "GET /image?src=2013-09/19/7255252-121-1.jpg&width=250 HTTP/1.1" 200 13512 0.033620 0.059528 False "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:28.0) Gecko/20100101 Firefox/28.0" "http://www.example.com/contact/"

where:

* `80.219.81.177` is the IP address of the client
* `29/May/2015:16:31:21` is the server's local time
* `GET /image?src=...` is the URL of the image (or page, JS, CSS file) requested
* `200` is the returned HTTP status code (200 = OK)
* `13512` is the size of the returned image (page, JS, CSS) file in bytes
* `0.033620` is the time taken in seconds to service the request in the QIS
  application
* `0.059528` is the time taken in seconds to service the request in Apache.
  This value includes, and is therefore always larger than the above value.
  It adds the time the request was queued for, and the time taken to send the
  image data back to the network.
* `False` means the image was not already cached (this image was newly generated)
* `Mozilla/5.0 ... Firefox/28.0` is the client's web browser version and operating
  system
* `http://www.example.com/contact/` is the web page that contains the image

You can therefore use a log file analysis tool such as
[Webalizer](http://www.webalizer.org/), [ALV](http://www.apacheviewer.com/),
or [AWStats](http://www.awstats.org/) to discover the answer to questions
such as:

* What are the slowest images being generated (largest times taken where the
  cached flag is `False`) and who is requesting them
* What is the overall level of traffic and bandwidth being served
* How many images over a certain size (in bytes) are being served
* How many errors are there (status code not 200) and what requests are
  triggering them
* What is the ratio of http to https traffic

### Benchmark script

As of v1.29, QIS now comes with a benchmarking script that you can use to run
repeatable tests against your image server. You'll need to try out the script to
come up with parameter values that test your server appropriately, but then you
can change various tuning values to see how they impact your response times or
overall capacity.

See the [benchmarking guide](benchmark.md) for more information.
