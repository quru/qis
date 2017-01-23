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
so that running it is easiest using `docker-compose`.

See the `docker-compose.yml` file in the parent directory for a sample configuration.
Running the sample requires a couple of environment variables:

	# Create a location for storing the QIS persistent data (database and images)
	$ mkdir qis_data
	$ export QIS_DATA_DIR=$(pwd)/qis_data
	
	# Set the hostname to use for the web server
	$ export QIS_HOSTNAME=$(hostname)

Ensure that no other services are already running on port 80 or 443,
then you can run the QIS services can all together with:

	$ cd <path to docker-compose.yml>
	$ docker-compose up -d

To check that everything is running, run:

	$ docker-compose ps
	
	       Name               Command        State                    Ports
	-----------------------------------------------------------------------------------------
	docker_qis_as_1      /run-qis.sh         Up      0.0.0.0:443->443/tcp, 0.0.0.0:80->80/tcp
	docker_qis_cache_1   /run-memcached.sh   Up      11211/tcp
	docker_qis_db_1      /run-postgres.sh    Up      5432/tcp

And you should now be able to access QIS at http://localhost/ in your web browser.
On first run, check the `qis.log` file to find the password for the `admin` user:

	$ cat $QIS_DATA_DIR/logs/qis/qis.log
