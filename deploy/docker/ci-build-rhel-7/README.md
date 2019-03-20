# CI Build Image - Red Hat Enterprise Linux 7

This is a development environment for building QIS-related software packages.
It runs an SSH service so that CI build servers can connect remotely.

### To build

Red Hat Enterprise systems require a subscription to use, which can be either
a corporate or a developer license. Pass through your Red Hat account details
as build arguments as shown below:

    $ cd <this directory>
    $ sudo docker build --build-arg RH_SUBS_USER=<RH username> --build-arg RH_SUBS_PASSWORD=<RH password> --build-arg AUTHORIZED_KEY="$(cat ~/.ssh/id_rsa.pub)" --tag quru/qis-ci-build-rhel-7 .

If you require authentication to pull the RHEL image, run:

	$ sudo docker login registry.access.redhat.com

Enter your Red Hat account username and password, then re-run the build command.

When you no longer need the image, or when it is superseded by a new version,
remove the subscription at https://access.redhat.com/management/systems or
by running `subscription-manager unregister` before deleting the old image.

### To run stand-alone

    $ sudo docker run -d quru/qis-ci-build-rhel-7
    $ ssh build@<IP of container>

### To run with a build server

Build the image with build arg `AUTHORIZED_KEY` containing the SSH public key of
your build server. Then:

    $ sudo docker run -d -p 9022:22 quru/qis-ci-build-rhel-7
    # Open port 9022/tcp on the firewall of your docker host
    # Set your build server to connect as build@<docker host> on port 9022

    # Optional - customise the container
    $ sudo docker exec -ti <container ID> /bin/bash
    # Add more SSH public keys into .ssh/authorized_keys
    [build@0ce64dbed542 ~]$ vi .ssh/authorized_keys
    # Install any packages required by your build server, e.g.
    [build@0ce64dbed542 ~]$ sudo yum install -y java
    [build@0ce64dbed542 ~]$ exit
