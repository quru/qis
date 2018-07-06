# Tuning the QIS installation

The install guide contains enough information to get you going (hopefully!),
but if you want to ensure your image server is being fully utilised, this guide
goes into more detail.

## Apache - mod_wsgi module

The mod_wsgi documentation is comprehensive and well written, so the starting
point is to go to [modwsgi.readthedocs.io](https://modwsgi.readthedocs.io/)
and have a read there.

QIS uses the "daemon mode" of mod_wsgi as it offers several advantages, including
easier configuration and higher performance out of the box.

Tuning the server capacity in daemon mode is a simple case of choosing how many
mod_wsgi processes you want to have running, and how many threads you want each
process to handle. One mod_wsgi thread can service one web request (but see below
for how this relates to the Apache workers). The size of mod_wsgi's "worker pool"
is fixed, with the appropriate number being determined by how the application
under load uses the CPU or allocates memory.

mod_wsgi's daemon mode threads are Python threads rather than native threads.
Python threads have a reputation for poor performance due to the use of internal
data locks, therefore it would seem best to keep the number of threads per process
fairly low (e.g. below 20). If you require more workers, increase the number of
processes instead.

As a guide to the number of mod_wsgi processes, allocate no more than the
number of CPU cores in your server, minus 1 if Memcached runs on the same server,
minus 1 if Postgres runs on the same server. So for example, on a 4 core CPU
running all the software, set 2 mod_wsgi processes. On an 8 core CPU running
all the software, set 4 to 6 mod_wsgi processes. Choose the lower number if your
server frequently has to generate new images, or the higher number if most of
your images (90% or more) are served from cache. See the _QIS system reports_
section for how to find out the percentage of images coming from cache.

Set the number of mod_wsgi processes and threads in the Apache configuration
files:

* `/etc/httpd/conf.d/qis.conf` (HTTP service)
* `/etc/httpd/conf.d/qis-ssl.conf` (HTTPS service)

The actual conf file location varies by operating system (e.g. `/etc/apache2`,
`/etc/httpd/sites-enabled/`, etc).

## Apache - choice of MPM

The installed Apache multi-processing module (MPM) determines whether Apache
itself uses multiple processes or multiple threads, or both, to handle client
requests.

The mod_wsgi documentation recommends using the worker MPM, but we have seen no
problems using the prefork MPM (which is the default on some platforms). In fact
when testing a normal QIS workload, prefork and worker perform almost identically.
The worker MPM uses a little less memory, because it creates 1 thread per worker
instead of 1 process per worker. The event MPM (a variant of worker) also works
fine.

How to set or change the Apache MPM varies by operating system. You can see which
MPM is currently enabled by running:

	$ httpd -V
	Server version: Apache/2.4.6 (Red Hat Enterprise Linux)
	...
	Server MPM:     prefork
	  threaded:     no
		forked:     yes (variable process count)

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
[Strip Down Apache to Improve Performance & Memory Efficiency](https://haydenjames.io/strip-apache-improve-performance-memory-efficiency/).

## Apache - MPM tuning

See the _mod_wsgi tuning settings vs Apache tuning settings_ section below for
a guide to how many Apache workers you will need once your mod_wsgi configuration
is done. The MPM tuning settings are then typically found or can be set in one
of these locations:

* `/etc/httpd/conf/http.conf` - Apache's main conf file (CentOS / Red Hat 7)
* `/etc/httpd/conf.modules.d/00-mpm.conf` - MPM conf file (CentOS / Red Hat 7)
* `/etc/apache2/apache2.conf` - Apache's main conf file (Debian / Ubuntu)
* `/etc/apache2/mods-enabled/mpm_<MPM>.conf` - MPM conf file (Debian / Ubuntu)

For the prefork MPM tuning settings, read:

* [Apache 2.4](https://httpd.apache.org/docs/current/mod/prefork.html)
* [Apache 2.2](https://httpd.apache.org/docs/2.2/mod/prefork.html)

For the worker MPM tuning settings, read:

* [Apache 2.4](https://httpd.apache.org/docs/current/mod/worker.html)
* [Apache 2.2](https://httpd.apache.org/docs/2.2/mod/worker.html)

For the event MPM tuning settings, read:

* [Apache 2.4](https://httpd.apache.org/docs/current/mod/event.html)
* [Apache 2.2](https://httpd.apache.org/docs/2.2/mod/event.html)

Beware that there are various rules, guidelines, and dependencies between the MPM
settings, the settings are different between Apache 2.2 and 2.4, and some of the
same configuration values have different meanings for different MPMs. Apache 2.4
thankfully improves this situation over Apache 2.2.

The "correct" values for MPM tuning depend on the types of image QIS that will be
serving (small+fast or large+slow) and the traffic levels of your server. You can
watch Graham Dumpleton's (the mod_wsgi author) PyCon talks for some interesting
insights into the effects of these settings, and also what not to do. Links to
these videos are in the _mod_wsgi tuning settings vs Apache tuning settings_
section below.

## Apache - KeepAlive

Enabling keep-alive means that an Apache worker will hold open the connection to
a client for a number of seconds, in the expectation that they will make further
requests. If they do, this leads to increased performance for the client via the
re-use of an already established "pipeline". If they don't, the Apache worker is
needlessly tied up in an idling state until the keep-alive timeout occurs. Apache's
event MPM attempts to minimise this problem.

In QIS, a web page typically has multiple images, therefore the default settings
in `qis.conf` and `qis-ssl.conf` enable keep-alive in the expectation of receiving
multiple requests from each client. The timeout value is set low (3 seconds by
default) to try and avoid capacity problems resulting from tied-up Apache workers.

If your web server is reaching the `MaxClients` limit in Apache while not being
maxed-out, disabling keep-alive will likely allow you to serve more traffic.
You can also try leaving keep-alive in place but switching to the event MPM.

## Apache - access logs

The standard QIS configuration enables logging of all QIS traffic. You can disable
this if you wish in the `qis.conf` and `qis-ssl.conf` Apache configuration files.

With access logs enabled, be sure to configure _logrotate_ to prevent the logs
growing in size to unreasonable levels. A busy web site can generate a gigabyte
access log in just a day. See the [install guide](install.md) for how to do this.

## mod_wsgi tuning settings vs Apache tuning settings

In Apache's main `http.conf` we can set values for `ServerLimit`, `MaxClients`,
and so on. In `qis.conf` we can set the mod_wsgi `WSGIDaemonProcess` number of
processes and threads.

But for a given number of WSGI connections, what should the Apache settings be?
Does changing one conf file have some effect on the other? If we configure our
desired capacity for mod_wsgi, do the Apache settings even matter?

Despite the generally excellent mod_wsgi documentation, there is very little
information to be found in terms of how these two tuning sections affect each
other. After many hours of searching, the answer is that they are separate but
related configurations. Increasing the number of Apache workers does not increase
the capacity of mod_wsgi or vice versa. However the 2 areas are related, and do
need to be tuned together.

In mod_wsgi's recommended daemon mode, the Apache workers are serving 2 purposes:

* Serving requests for _static_ content, resources such as robots.txt, static images,
  static HTML pages, JavaScript and CSS files. These requests bypass mod_wsgi.
* When serving requests for _dynamic_ content, the Apache workers act as proxies
  to and from mod_wsgi's own worker pool.

The second point indicates that for each mod_wsgi connection we require at least
one Apache worker to act as a proxy. Adding in the first point, we can see that
Apache must be configured to support at least the total WSGI pool size **plus**
the expected static file traffic, in terms of `MaxClients`.

In fact, Graham Dumpleton (the mod_wsgi author) suggests an approximate ratio of 4
Apache workers to 1 mod_wsgi connection. As discussed in his PyCon 2013 presentation,
this is so that the WSGI module can return data to one Apache worker straight away,
and then switch to servicing the next waiting Apache worker. The Apache workers then
take care of pushing data to slow networks and waiting for keep-alive clients, without
holding up a valuable mod_wsgi connection. The optimum ratio will actually depend on
the size of each request, the network speed of clients, server bandwidth and keep-alive
settings.

The mod_wsgi daemon mode process + thread pool is of a fixed size and is not affected
by the Apache tuning settings. It should be set to the maximum number of concurrent
Python requests you want to support without overloading the server. Unlike the number
of Apache workers, this pool size is never increased or decreased as the web traffic
changes.

For further information on Apache tuning with mod_wsgi, see Graham Dumpleton's PyCon
talks:

* https://pyvideo.org/pycon-au-2012/web-server-bottlenecks-and-performance-tuning-0.html
* https://pyvideo.org/pycon-us-2013/making-apache-suck-less-for-hosting-python-web-ap.html

While the 4:1 ratio came from a support forum post: 
https://groups.google.com/d/msg/modwsgi/rufSwTh6PLI/hrHJqRSXJy8J

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

## Image processing

<a name="pillow"></a>
### Pillow library (QIS Standard Edition)

QIS ships with the Python Pillow imaging library as standard. This always uses
8 bits per quantum (pixel RGBA component) and is therefore roughly equivalent
to using the alternative ImageMagick library (see below) in Q8 mode.

There is one major factor affecting the performance of image generation in Pillow,
which is whether or not to perform gamma correction when resizing. This problem
is described with examples at http://www.ericbrasseur.org/gamma.html

By default QIS enables gamma correction so that resized images look correct,
however the way this is currently implemented in QIS is very expensive in terms
of performance. For a large speed-up at the expense of colour accurancy, you
can disable gamma correction by adding this line to your QIS `local_settings.py`
file:

	IMAGE_RESIZE_GAMMA_CORRECT = False

<a name="imagemagick"></a>
### ImageMagick library (QIS Premium Edition)

ImageMagick by default is compiled in "Q16" mode, which means it uses 16 bits per
quantum (pixel RGBA component) resolution during imaging operations rather than
the 8 of Pillow. If you re-compile ImageMagick as Q8, performance will improve and
memory consumption will be approximately halved, at the expense of some image and
colour accuracy.

According to https://www.imagemagick.org/discourse-server/viewtopic.php?f=2&t=22932

> We recommend Q16. It is a nice balance between performance, memory consumption,
> and mathematical precision. Q8 uses less memory and improves performance.
> ... You probably don't need a Q32 release.

If you wish to trade off some colour precision in return for the performance
gains of Q8, you'll need to compile ImageMagick from source as described at
https://www.imagemagick.org/script/advanced-unix-installation.php . For example:

	$ ./configure --with-quantum-depth 8 --with-threads --with-rsvg --with-xml \
	              --without-dps --without-perl --without-x
	$ make
	$ sudo make install

ImageMagick performs gamma correction in a much faster way than the Pillow
implementation. Therefore while you can disable gamma correction with the
`IMAGE_RESIZE_GAMMA_CORRECT` setting, you will only see around a 5 to 10%
performance improvement.

## QIS settings

The following application settings, which you can override in your
`local_settings.py` file, may have an impact on the performance and capacity
of your server:

* `IMAGE_RESIZE_QUALITY` - setting a value of `1` or `2` will speed up resizing
  operations and reduce the CPU load on your server
* `IMAGE_RESIZE_GAMMA_CORRECT` - setting this to `False` will greatly speed up
  image resizing in Pillow, and slightly with ImageMagick
* `AUTO_PYRAMID_THRESHOLD` - you can disable this feature by setting a value of
  `0` to prevent (possibly unnecessary) pre-emptive image generation
* `PDF_BURST_TO_PNG` - you can disable this feature by setting a value of `False`
  to prevent the automatic creation of images from PDF files (Premium Edition only)

## Image operations

By tuning some of the image parameters in your templates (including your default
template) you may be able to create smaller and/or faster images at the same
quality. From the [image URL](image_help.md) or template administration area
you can experiment with these options:

* *Strip meta-data* - if you do not require embedded colour profiles and meta-data
  e.g. the camera make and model, enabling this setting can reduce the generated
  image sizes
* *File format* - changing the image format can result in faster processing, smaller
  file sizes, or better image quality
* *JPG/PNG compression* - For `jpg` images, lowering the quality will reduce the
  generated image sizes. For `png` images the visual quality is always the same,
  but the compression level affects the image creation time.
  * In the Premium Edition you can also change the PNG filter type for `png` images,
    which can greatly affect speed and file sizes, but note that the optimal value
    for one image may not be the best choice for another
* *Client caching duration* - if your images do not change once uploaded,
  increase this value to 30 days (`2592000`) or even 1 year (`31536000`), to instruct
  web browsers to keep your images in their local cache instead of re-fetching them

## An example

This real life example is a large server with 10 CPU cores and 56GB of RAM, running
Red Hat Enterprise Linux 6.5. It is sat behind a proxy server that handles HTTPS
connections with the outside world, so that almost all the internal traffic arrives
as plain HTTP requests.

### Memory allocation

We will aim for the following allocation of RAM:

1 GB for the operating system and miscellaneous processes  
2 GB for Postgres shared cache and client processes  
4 GB for mod_wsgi processes (9 x 0.5GB)  
45 GB for Memcached  
4 GB reserved as a buffer for occasional large imaging operations, but used by
the operating system when "free" for disk caches and buffers (this is useful for
QIS, but actually expected by Postgres)  
Total 56GB

We need to leave enough RAM free to prevent the o/s swapping. It is particularly
important that the Memcached database fits entirely into RAM!

Note: some swap space may still be used under normal conditions - see the
_checking memory use_ section below.

### mod_wsgi config

Since the mod_wsgi/http/python processes (incorporating Pillow/ImageMagick) are
the most CPU intensive, allocate at least 1 CPU core per mod_wsgi process. Leaving
aside 3 CPU cores for the operating system, Memcached, and Postgres, this leaves 7
for mod_wsgi. Because this particular server deals with very little HTTPS traffic,
we will specify 2 processes in `qis-ssl.conf` but ignore these when considering
the server load.

	Apache conf	        WSGIDaemonProcess
	                processes        threads
	qis.conf            7              15
	qis-ssl.conf        2              10

All HTTP traffic then is served by (7 x 15) + (2 x 10) = 125 mod_wsgi threads.

### Apache config

Red Hat 6 ships Apache with the prefork MPM (Multi-Processing Module) by default,
and we haven't changed this. In tests, the worker MPM uses the same amount of
memory and gives on average the same performance.

This server sits alongside a web site that displays several images per page,
therefore we shall leave keep-alive enabled, but set it to a fairly short value
so that Apache does not hold open idle client connections for long. If you see
"max clients reached" in the Apache `error_log` file, you can either increase the
number of Apache workers, disable keep-alive, or consider switching to Apache's
event MPM.

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

Postgres (or any database server) can only serve a finite number of connections anyway,
especially simultaneous writes. So as long as database activity does not take up
the entire request time and connections are released quickly, then there is no harm
in having a connection pool size lower than the expected number of concurrent site
users. The pooling software will take care of waiting for a connection to become
free if none are available. In QIS, the database activity time is typically a small
part of the whole request time, so the pool can usually be expected to contain free
connections.

### Postgres

Aiming roughly for a total memory usage of 2GB, `postgresql.conf` can be tuned
as follows:

	Setting                      Value   Why
	max_connections              120     As described above, we are allowing for 100 connections plus an overflow
	shared_buffers               2GB     Primary working memory, the default value is only 32MB.
	                                     Lower than the "recommended" value as we are reserving much of the server for Memcached and mod_wsgi
	wal_buffers                  16MB    Recommended value for our shared_buffers setting (and the default on Postgres 8.4+)
	checkpoint_segments          16      Reasonable value for our settings
	checkpoint_completion_target 0.9     As recommended in the Postgres documentation when checkpoint_segments has been adjusted
	effective_cache_size         4GB     Lower than the "recommended" value as we are reserving much of the server for Memcached and mod_wsgi
	default_statistics_target    100     Recommended value (and the default on Postgres 8.4+)

See also [the Postgres tuning documentation](https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server)
and the online [pgtune](https://pgtune.leopard.in.ua/) utility.

Later note: in hindsight, setting `shared_buffers` to 2GB is probably over-the-top,
and a value of 1GB or 512MB should suffice even on a large and busy server.

### Memcached

Memcached needs locking down to only accept local connections, and needs the
memory limit setting in `/etc/sysconfig/memcached`:

	OPTIONS="-l 127.0.0.1"
	CACHESIZE="45000"

This server takes approximately 2 days to fill the cache to its maximum size.
When full, the 45 GB process looks like this:

	$ ps -u memcached euf
	USER   PID  %CPU %MEM VSZ      RSS      TTY STAT START   TIME COMMAND
	496    6204 1.0  75.7 46597100 43679944 ?   Ssl  Apr24 105:51 memcached -d -p 11211 -u memcached -m 45000 -c 1024 -l 127.0.0.1 -P /var/run/memcached/memcached.pid

### Checking memory use

If you're not too familiar with Linux memory management, first read the article
[Linux Memory Management - Low on Memory](https://linux-mm.org/Low_On_Memory),
otherwise you might see `MemTotal: 56GB, MemFree: 0.4GB` and think that you're
out of memory when you're not.

Check the size of your Memcached process to see whether the cache has reached its
limit. If it's not yet full, bear in mind the extra memory that is going to be used.

Get a brief overview of memory use with `free`:

	$ free -m
	             total       used       free     shared    buffers     cached
	Mem:         56348      55736        611          0        188       9898
	-/+ buffers/cache:      45648      10699
	Swap:         8015       2810       5205

Here the server is showing that it is using 45.6GB out of 56GB, which is broadly
in line with the numbers we aimed for. There is 10.7GB of "free" memory, but the
server is putting 10.1GB of that to good use by using it for buffers and filesystem
caching, leaving only 611MB sitting idle at that point in time.

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
  request e.g. JavaScript and CSS files. For these, see the Apache access logs.
* Number of images served - the number of images actually sent back to clients.
  This is usually less than _total image requests_ because of client-side web
  browser caching. If the client already has an up-to-date copy of the image,
  the server will quickly respond with a short `HTTP 304 Not modified` message.
* Percentage of images served from cache - in the context of serving images on
  a web site, this value should be high, 90% or more.
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

	80.219.81.177 [29/May/2015:16:31:21 -0100] "GET /image?src=2013-09/19/7255252-121-1.jpg&width=250 HTTP/1.1" 200 13512 33620 59528 False "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:28.0) Gecko/20100101 Firefox/28.0" "http://www.example.com/contact/"

where:

* `80.219.81.177` is the IP address of the client
* `29/May/2015:16:31:21` is the server's local time
* `GET /image?src=...` is the URL of the image (or page, JS, CSS file) requested
* `200` is the returned HTTP status code (200 = OK)
* `13512` is the size of the returned image (page, JS, CSS) file in bytes
* `33620` is the time taken in microseconds to service the request in the QIS
  application
* `59528` is the time taken in microseconds to service the request in Apache.
  This value includes, and is therefore always larger than, the above value.
  It adds the time the request was queued for, and the time taken to send the
  image data back to the network interface.
* `False` means the image was not already cached (this image was newly generated)
* `Mozilla/5.0 ... Firefox/28.0` is the client's web browser version and operating
  system
* `http://www.example.com/contact/` is the web page that contains the image

With this data you can therefore use a log file analysis tool such as
[Webalizer](http://www.webalizer.org/), [ALV](https://www.apacheviewer.com/),
or [AWStats](https://www.awstats.org/) to discover the answer to questions
such as:

* What are the slowest images being generated (largest times taken where the
  cached flag is `False`) and who is requesting them
* What is the overall level of traffic and bandwidth being served
* How many images over a certain size (in bytes) are being served
* How many errors are there (status code not 200) and what requests are
  triggering them
* What is the ratio of HTTP to HTTPS traffic

### Benchmark script

As of v1.29, QIS now comes with a benchmarking script that you can use to run
repeatable tests against your image server. You'll need to try out the script to
come up with parameter values that test your server appropriately, but then you
can change various tuning values to see how they impact your response times or
overall capacity.

See the [benchmarking guide](benchmark.md) for more information.
