# Memcached Docker Image

The in-memory cache server for QIS.

### To build

This is only required once (per release or version), and is an "internal" process
to be performed by the image maintainer.

	$ cd <this directory>
	$ docker build -t quru/qis-memcached .

To publish the image in Docker Hub, tag it with the application version and push it:

	$ docker images
	$ docker tag <image_id> quru/qis-memcached:<version>
	$ docker login
	$ docker push quru/qis-memcached

### To run stand-alone

To bind to the host's port 11211 with a 1GB cache size:

	$ docker run -d -p 11211:11211 --env MEMCACHED_SIZE=1024 quru/qis-memcached

### To run with QIS

Use the application's `Composefile` to run this container in combination with the others.
