# QIS on Docker

These instructions last updated 1st May 2015 for Docker 1.6 and Fedora 21.

TODO Outdated methods that need updating

- Fedora 21 is now outdated, later releases use `dnf` instead of `yum`
- Download QIS source from the GitHub releases (zip/tar.gz), do not require local files
- No need for GitHub SSH key in the Build image since the main repo went public
- Use https://certbot.eff.org/#fedora23-apache to install a proper SSL certificate
- Use a web hook in DockerHub to automatically build the image from the Dockerfile in GitHub

TODO For Docker 1.12

- Use a Composefile to create and run all the containers
- Dockerfiles can now take arguments (ARG and --build-arg) - may simplify the build
- Proper handling of logs
- Possibly - use readonly filesystem apart from volumes and temp files (see `run --tmpfs`)
  (can use `docker diff` to check if any other files get written)
- Change volumes to use `docker volume`
- Volumes can be shared and can specify a back-end plugin for e.g. Ceph storage
- Change container linking to use `docker network`
- Possibly - set up a private network for internal communications
- Networking - find out how to deploy across multiple hosts
- Implement `HEALTHCHECK` container tests
- Deployment under Swarm mode using a bundle file (Compose can create these)
  (though note there are a currently lot of reported issues with Swarm mode)

### Notes

Fedora 21 is significantly smaller than Fedora 20, and has packages for:

* ImageMagick 6.8.8.10-6
* Memcached 1.4.17-3
* Postgres 9.3.6-1

The small distribution size means that you need to install several packages
(`tar`, `zip`, etc) that you would normally expect to be included.

### Docker change notes

Docker 1.5 added named Dockerfiles, IPv6 support, read-only container file systems.  
Docker 1.6 includes new logging facilities, the ability to set ulimits for containers.
Docker 1.7 added multi-host networking (beta, `docker network`), ZFS support, better volumes (beta).
Docker 1.8 added signed images, volume plugins, and 2-way host-container file copy.
Docker 1.9 added image build args, multi-host networking (GA), `docker volume` commands (GA),
           separate Swarm utility (GA).
Docker 1.10 added new image IDs and storage, add disk I/O resource limits, major networking
            and volumes fixes, internal DNS, Compose support for networks and volumes.
Docker 1.11 was a major refactor of the daemon.
Docker 1.12 Splits CLI and daemon binaries, adds orchestration - merges Swarm into the engine
            (`docker node`, `docker service`, `docker swarm`),
            adds core plugins (beta, `docker plugin`), adds disk quota support.

## Creating the QIS build image

This Docker image provides a temporary build/development environment that can be used
to build and test QIS on Fedora. The resulting QIS binaries can then be used to create
the AS Docker image as described below. Hopefully that makes sense.

	mkdir tmp
	cd tmp
	cp /path/to/QIS-Build-Dockerfile.txt .
	cp /path/to/your_public_ssh_key git_ssh_key
	sudo docker build -f QIS-Build-Dockerfile.txt -t "qis-build" .

Once built, **DO NOT PUBLISH THIS IMAGE!**, it contains your ssh key and a hard coded
password for the `qis` user.

## Using the QIS build image to build and test QIS

Start an interactive (shell) session from the qis-build image:

	sudo docker run -ti --name="qis-build-container" qis-build /bin/bash

And then inside the session, run these instructions:

	cd qis
	sed -i -e 's/python2\.6/python2\.7/g' Makefile
	make distribute

Verify the result:

	ls -l dist
	...
	-rw-rw-r-- 1 qis qis  5873801 May  1 11:22 dependencies.tar.gz
	-rw-rw-r-- 1 qis qis 19340203 May  1 11:22 Quru Image Server-1.28.1.tar.gz

Then if you want to run the unit tests:

	# For sudo, the qis user's password is qispass
	sudo -u memcached /usr/bin/memcached -d
	# Start postgres and create the db user and an empty database
	sudo -u postgres pg_ctl -D /var/lib/pgsql/data -l /var/lib/pgsql/data/pg_log/postgres.log start
	psql -h localhost -U postgres -d postgres -c "CREATE ROLE qis WITH LOGIN PASSWORD 'qispass'"
	createdb -h localhost -U postgres --owner qis qis-cache-test
	createdb -h localhost -U postgres --owner qis qis-mgmt-test
	# Run the tests
	make test
	# Kill off the test aux processes (logger, stats, bg tasks)
	kill `ps aux | grep "python setup" | grep -v grep | awk '{print $2}'`

Exit the container:

	exit

Copy the QIS build files back onto the host:

	cd ..
	mkdir qis-f21 && cd qis-f21
	sudo docker cp qis-build-container:/home/qis/qis/dist/dependencies.tar.gz .
	sudo docker cp qis-build-container:/home/qis/qis/dist/Quru\ Image\ Server-1.28.1.tar.gz .
	cd ..

And optionally delete the container if you won't be building QIS again for a while:

	sudo docker rm qis-build-container

## Creating the CA docker image

To build the QIS cache service image:

	mkdir tmp
	cd tmp
	tar --strip-components=1 -xvf ../qis-f21/Quru\ Image\ Server-1.28.1.tar.gz
	cp deploy/docker/QIS-CA-Dockerfile.txt ./Dockerfile
	cp deploy/docker/dockerignore .dockerignore
	sudo docker build -t "quru/qis-memcached" .

Optionally tag the image name e.g. as 1.4.17:

	sudo docker images
	sudo docker tag <image_id> quru/qis-memcached:1.4.17

If desired later, push the image to dockerhub:

	sudo docker push quru/qis-memcached

## Creating the DB docker image

To build the QIS database service image:

	mkdir tmp
	cd tmp
	tar --strip-components=1 -xvf ../qis-f21/Quru\ Image\ Server-1.28.1.tar.gz
	cp deploy/docker/QIS-DB-Dockerfile.txt ./Dockerfile
	cp deploy/docker/dockerignore .dockerignore
	sudo docker build -t "quru/qis-postgres" .

Optionally tag the image name e.g. as 9.3.6:

	sudo docker images
	sudo docker tag <image_id> quru/qis-postgres:9.3.6

If desired later, push the image to dockerhub:

	sudo docker push quru/qis-postgres

## Testing the DB docker image

From local build tagged as above, or from dockerhub.

Run a new container to hold the data:

	# Note the echo command causes the container to exit immediately;
	#      the data volume is defined in the image (VOLUME in the dockerfile)
	#      otherwise we would need a -v <path> adding here too
	sudo docker run -d --name qis-db-data quru/qis-postgres echo 'QIS db data-only container'

Run a new container to provide the Postgres service:

	# Note the data container above (volumes-from) does not need to be running here
	sudo docker run -d --name qis-db --volumes-from qis-db-data -p 127.0.0.1:15432:5432 quru/qis-postgres

Connect to the running container:

	# The default password is "qispass", but this can be changed by adding
    # "--env PG_PASS=foo" to docker run, when the container is created.
	psql -h localhost -p 15432 -U qis -d qis-mgmt

Backing up the data container:

	See [the Docker documentation](https://docs.docker.com/userguide/dockervolumes/#backup-restore-or-migrate-data-volumes).

## Creating the AS docker image

To build the QIS application server image:

	mkdir tmp
	cd tmp
	mkdir -p lib/python2.7
	cd lib/python2.7
	tar -xvf ../../../qis-f21/dependencies.tar.gz
	cd ../..
	tar --strip-components=1 -xvf ../qis-f21/Quru\ Image\ Server-1.28.1.tar.gz
	cp deploy/docker/QIS-AS-Dockerfile.txt ./Dockerfile
	cp deploy/docker/dockerignore .dockerignore
	sudo docker build -t "quru/qis-web" .

Optionally tag the image name e.g. as 1.28.1:

	sudo docker images
	sudo docker tag <image_id> quru/qis-web:1.28.1

If desired later, push the image to dockerhub:

	sudo docker push quru/qis-web

## Running containers in production

Note that multiple env vars can be defined in a file and specified with `--env-file`.

	# These just need to be created once (they will exit immediately)
	sudo docker run -d --name qis-db-data quru/qis-postgres echo 'QIS db data-only container'
	sudo docker run -d --name qis-web-data quru/qis-web echo 'QIS web data-only container'

	# These need to be running
	sudo docker run -d --name qis-cache -m 8000m \
	     --env CACHESIZE=7500 \
	     quru/qis-memcached
	sudo docker run -d --name qis-db -m 2000m \
	     --volumes-from qis-db-data \
	     --env PG_PASS=givemeasecurepassword \
	     --env PG_MAX_CONNECTIONS=120 \
	     --env PG_SHARED_BUFFERS=750MB \
	     --env PG_EFFECTIVE_CACHE_SIZE=1500MB \
	     quru/qis-postgres
	sudo docker run -d --name qis-web -m 4000m \
	     --volumes-from qis-web-data \
	     --link qis-db:db --link qis-cache:cache \
	     -p 80:80 -p 443:443 \
	     --env HOSTNAME=images.example.com \
	     --env HTTP_PROCESSES=4 \
	     --env HTTPS_PROCESSES=4 \
	     quru/qis-web

	# On first run, print out and note the admin password
	sudo docker run -t --rm --volumes-from qis-web-data quru/qis-web /bin/bash -c 'cat /opt/qis/logs/qis.log'

About the runtime settings:

* Cache container
	* Set `CACHESIZE` to about the RAM allocation minus 500MB
* Database container
	* Set `PG_SHARED_BUFFERS` to about 40% of the RAM allocation
	* Set `PG_EFFECTIVE_CACHE_SIZE` to about 75% of the RAM allocation
	* Set `PG_MAX_CONNECTIONS` based roughly on the 2 QIS `DATABASE_POOL_SIZE` settings
	  multiplied by the number of HTTP + HTTPS processes. Higher numbers require more
	  RAM, and a value much above 150 is probably going to be counter-productive.
* Web container
	* Allow at least 1 CPU core per HTTP/HTTPS process
	* Set the RAM allocation to allow for around 500MB per process
	* Do not set the HTTP/HTTPS threads above 20 per process

## Docker problems

### Setting memory limits
Running Docker with e.g. `docker run -m 1g ...` you are likely to get
_"WARNING: Your kernel does not support swap limit capabilities. Limitation discarded."_

According to http://programster.blogspot.co.uk/2014/09/docker-implementing-container-memory.html
this can be fixed by running this one-time script (for Ubuntu 14.04) and then rebooting the server.

	SEARCH='GRUB_CMDLINE_LINUX=""'
	REPLACE='GRUB_CMDLINE_LINUX="cgroup_enable=memory swapaccount=1"'
	FILEPATH="/etc/default/grub"
	sudo sed -i "s;$SEARCH;$REPLACE;" $FILEPATH
	sudo update-grub
	echo "You now need to reboot for the changes to take effect"

### Logging
_New logging facilities in Docker 1.6!_
Currently (Docker 1.2) there is no sane way of handling log rotation in a Docker container,
so QIS access logs are disabled. We might need to disable the error log too.
For Docker logging, see https://github.com/docker/docker/issues/7195
But the main issue is that the httpd process cannot be HUPd to rotate the logs
as the container would then exit. To fix this today, we could:
 - Run supervisord as the main container process
 - Get supervisor to launch and httpd and crond
 - Call logrotate from /etc/cron.daily
 - Configure log rotation from /etc/logrotate.d/httpd

Redirecting the httpd logs to stdout or stderr would enable the logs to be
collected by the host's Docker daemon, but this adds overhead during heavy
logging and the Docker log file itself is an ever-growing JSON file.

### Inspecting a running container
_Now possible in Docker 1.3!_
Currently (Docker 1.2) there is no easy way of logging into a running container to inspect
and debug it. Docker provides 'attach' and 'logs' commands, but there is no
interaction to perform with e.g. the httpd process, and there is no stdout and
stderr from these types of process either, as they write their own log files.
Running sshd in containers is discouraged but is currently the best way of
solving this problem. As for logging (above) we could use supervisord as the main
container process to achieve this. Coming soon is a Docker 'exec' command,
see pull request https://github.com/docker/docker/pull/7409
which will then allow sshd (or a screen command) to be started and stopped
on-demand inside the container.

### Data volumes
Data volumes cannot currently reside on a different host. Flocker provides one
solution to this, and for migrating data containers to different hosts.

Partial answer: https://docs.docker.com/articles/ambassador_pattern_linking/

I expect this to be an active area of change and improvement in the Docker 1.x series.

### Application tuning
E.g. Postgres.conf, Apache tuning.

We have built in some reasonable tuning capabilities through the use of Docker
ENV parameters when running the containers, but many settings remain at their
default values.

### Docker storage drivers (back ends)
Docker bug 6980 (ref below) is caused by the AUFS backend, which appears to be
the default storage driver on Ubuntu even though it shouldn't be. According
to http://stackoverflow.com/a/24772588/1671320 the default backend should be
devicemapper. A description of AUFS here also refers to AUFS as not suitable
for production use: http://www.projectatomic.io/docs/filesystems/

Check the storage backend with 'docker info' before going too far - you might
want to change it. For how to switch the storage driver, see:
http://muehe.org/posts/switching-docker-from-aufs-to-devicemapper/

### Docker bugs
cap_set_file error doing a 'yum update' in a container on ubuntu hosts with
the AUFS storage driver: https://github.com/docker/docker/issues/6980
(workaround is to build the images on a different host o/s or change the storage driver)

docker cp does not work with volumes https://github.com/docker/docker/issues/1992
(workaround is to find the files on the host itself using docker inspect to get the volume path)

docker build sometimes fails with "Error getting container ... from driver devicemapper".
Just re-run the build and it will carry on from where it left off.
This seems to be fixed in Docker 1.7 according to https://github.com/docker/docker/issues/4036

### Orphaned volumes
Performing a 'docker rm -v <container>' should delete the associated volumes
when deleting a container, but I'm seeing lots of volumes left behind. This
might be something I'm doing wrong, will try to figure it out. There is a
script to delete orphaned volumes here:
https://gist.github.com/mindreframer/7787702
which I have updated for Docker 1.2 (which does things differently):
https://gist.github.com/fozcode/f7919f639a3ab01096e9

As of Docker 1.9 you can check for ophaned volumes with:
`docker volume ls --filter dangling=true`
