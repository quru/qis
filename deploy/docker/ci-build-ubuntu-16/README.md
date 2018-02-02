# CI Build Image - Ubuntu 16

This is a development environment for building QIS-related software packages.
It runs an SSH service so that CI build servers can connect remotely.

### To build

    $ cd <this directory>
    $ sudo docker build --build-arg AUTHORIZED_KEY="$(cat ~/.ssh/id_rsa.pub)" --tag quru/qis-ci-build-ubuntu-16 .

### To run stand-alone

    $ sudo docker run -d quru/qis-ci-build-ubuntu-16
    $ ssh build@<IP of container>

### To run with a build server

    $ sudo docker run -d -p 9024:22 quru/qis-ci-build-ubuntu-16
    $ ssh -p 9024 build@localhost
    # Add the SSH key of your build server into .ssh/authorized_keys
    [build@0ce64dbed542 ~]$ vi .ssh/authorized_keys
    # Install any packages required by your build server, e.g.
    [build@0ce64dbed542 ~]$ sudo apt-get -y install default-jdk
    [build@0ce64dbed542 ~]$ exit
    # Open port 9024/tcp on the firewall of your docker host
    # Set your build server to connect as build@<docker host> on port 9024
