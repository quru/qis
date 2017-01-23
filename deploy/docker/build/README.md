# QIS Build Docker Image

This is a development environment for building QIS-related software packages.
Basically it is the application server image with additional development
tools and libraries. It does not perform any function by itself.

### To build

	$ cd <this directory>
	$ docker build -t quru/qis-build .

### To run stand-alone

	$ docker run -ti quru/qis-build
	$ python -c 'print("go ahead and build something")'
