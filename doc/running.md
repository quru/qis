# Running QIS

* [On your own server](#diy)
* [On Docker](#docker)
* [On Amazon Web Services (AWS)](#aws)
* [Multi-server deployments](#architecture)

<a name="diy"></a>
## Manual installation

If you have your own server, and the thought of installing operating system
packages and editing configuration files makes you happy, you can install QIS
and its components manually by following the [installation guide](install.md).

<a name="docker"></a>
## Running in Docker

For a much simpler deployment, QIS can be deployed on Docker. Quru provides 3
Docker images and a `docker-compose` script that will set up and run everything
for you on a single host.

### Instructions - Docker

TODO

### Customising the deployment

TODO

If you are familiar with Docker commands, see the
[docker-compose](../deploy/docker/docker-compose.yml) script and the
[application server image notes](../deploy/docker/qis-as/README.md) for more information.

You can find pre-built QIS images on the [Docker Hub](https://cloud.docker.com/u/quru/),
or you can build them locally from the files in GitHub by running `docker-compose build`.

<a name="aws"></a>
## Running on Amazon Web Services (EC2)

Quru provides an Amazon Machine Image (AMI) that can be used to run a pre-installed
copy of QIS on Amazon's EC2 service. The current AMI is `ami-044f56e3f927a8f22`
in the EU West (Ireland) region.

### Instructions - AWS

TODO

### Customising the deployment

TODO

<a name="architecture"></a>
## Deployment architecture for high traffic / high loads

QIS depends on the following open source tools and applications:

* Linux operating system
* Python 3.4 or above - to run the QIS application code
* Apache 2.4 - the web server
* mod_wsgi Apache module - to run the QIS Python application inside Apache
* Memcached - for caching generated images and frequently accessed data
* PostgreSQL 9.2 or above - to store image and folder data, users, groups,
  folder permissions and statistics

And additionally for the Premium Edition:

* ImageMagick - image processing library
* Ghostscript - PDF processing library

For how these should be installed and configured,
see the [install guide](install.md) and the [tuning guide](tuning.md).

For low or predictable loads, you can install all of these on one server. QIS
in production has served 5 million images per day from a single server, albeit
a fairly powerful one (8 cores and 32GB RAM, mostly scaling and cropping digital
camera photographs, with 90% of requests served from cache).

For high or variable loads, you may want to separate out the system into web and
storage tiers. Web servers scale better as multiple small servers (rather than
one large server), and image processing is typically CPU intensive, therefore it
is primarily the web tier that should be scaled out. As an example:

![Example web and storage tiers](images/arch_scaling.jpg)

This system can be scaled up and down on-demand (elastic scaling) by adding or
removing web servers at any time. Memcached can run either on a separate server
if the network is fast, on one "primary" web server, or configured as a cluster
across all the permanent web servers. QIS enables
[consistent hashing](https://en.wikipedia.org/wiki/Consistent_hashing) when
using a Memcached cluster, but you should avoid adding/removing servers to/from
the cluster because of the re-distribution of keys that will occur.

The storage tier is harder to scale. Although in general QIS does not use the
PostgreSQL database heavily, storing the Postgres data files on a fast disk
or SSD is advantageous. The v9.x releases of Postgres have seen some significant
performance improvements, so always use the latest version available. PostgreSQL
can also be clustered and replicated.
