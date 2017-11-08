# CI Build Image - CentOS 7

This is a development environment for building QIS-related software packages.
It runs an SSH service so that CI build servers can connect remotely.

### To build

	$ cd <this directory>
	$ docker build --build-arg AUTHORIZED_KEY="$(cat ~/.ssh/id_rsa.pub)" --tag quru/qis-ci-build-centos-7 .

### To run stand-alone

	$ docker run quru/qis-ci-build-centos-7
	$ ssh build@<IP of container>
