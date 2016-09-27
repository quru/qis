# PostgreSQL Docker Image

The back-end database server for QIS.

### To build

This is only required once (per release or new version), and is an "internal"
process to be performed by the image maintainer.

	$ cd <this directory>
	$ docker build -t quru/qis-postgres .

To publish the image in Docker Hub, tag it with the application version and push it:

	$ docker images
	$ docker tag <image_id> quru/qis-postgres:<version>
	$ docker login
	$ docker push quru/qis-postgres

### To run stand-alone

To bind Postgres to the host's port 5432 with a 1GB RAM allocation:

	$ docker volume create --name qis-db-data
	
	$ docker run -d -p 5432:5432 -v qis-db-data:/var/lib/postgresql/9.5/data -m 1000m \
	  --env PG_PASSWORD=<password> \
	  --env PG_SHARED_BUFFERS=250MB \
	  --env PG_EFFECTIVE_CACHE_SIZE=750MB \	  
	  quru/qis-postgres

:warning: Note that supplying the database password as an environment variable,
while convenient, is far from ideal in terms of security. The problems with this
(compared with other approaches) is described well at:
http://elasticcompute.io/2016/01/21/runtime-secrets-with-docker-containers/

The Docker project has a discussion about this topic at:  
https://github.com/docker/docker/issues/13490

### To run with QIS

Use the application's `Composefile` to run this container in combination with the others.
