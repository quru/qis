# QIS Application Server Docker Image

The main web / application server for QIS.

### To build

This is only required once (per release or new version), and is an "internal"
process to be performed by the image maintainer.

	$ cd <this directory>
	$ docker build -t quru/qis-as .

To publish the image in Docker Hub, tag it with the application version and push it:

	$ docker images
	$ docker tag <image_id> quru/qis-as:<version>
	$ docker login
	$ docker push quru/qis-as

### To run

A QIS web container requires linking to Memcached and Postgres containers,
so that running it is easiest using `docker-compose`. The `docker-compose.yml`
file in the parent directory provides a sample configuration.

See the guide `doc/running.md` for how to run QIS using `docker-compose`.
