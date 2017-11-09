# CI Build Image - Red Hat Enterprise Linux 7

This is a development environment for building QIS-related software packages.
It runs an SSH service so that CI build servers can connect remotely.

### To build

Red Hat Enterprise systems require a subscription to use, which can be either
a corporate or a developer license. Pass through your Red Hat account details
as build arguments as shown below:

	$ cd <this directory>
	$ sudo docker build --build-arg RH_SUBS_USER=<RH username> --build-arg RH_SUBS_PASSWORD=<RH password> --build-arg AUTHORIZED_KEY="$(cat ~/.ssh/id_rsa.pub)" --tag quru/qis-ci-build-rhel-7 .

When you no longer need the image, or when it is superseded by a new version,
remove the subscription at https://access.redhat.com/management/systems or
by running `subscription-manager unregister` before deleting the image.

### To run stand-alone

	$ sudo docker run -d quru/qis-ci-build-rhel-7
	$ ssh build@<IP of container>
