# CI Build Image - CentOS 7

This is a development environment for building QIS-related software packages.
It runs an SSH service so that CI build servers can connect remotely.

### To build

    $ cd <this directory>
    $ sudo docker build --build-arg AUTHORIZED_KEY="$(cat ~/.ssh/id_rsa.pub)" --tag quru/qis-ci-build-centos-7 .

### To run stand-alone

    $ sudo docker run -d quru/qis-ci-build-centos-7
    $ ssh build@<IP of container>

### To run with a build server

    $ sudo docker run -d -p 9023:22 quru/qis-ci-build-centos-7
    $ ssh -p 9023 build@localhost
    # Add the SSH key of your build server into .ssh/authorized_keys
    [build@0ce64dbed542 ~]$ vi .ssh/authorized_keys
    # Install any packages required by your build server, e.g.
    [build@0ce64dbed542 ~]$ sudo yum install -y java
    [build@0ce64dbed542 ~]$ exit
    # Open port 9023/tcp on the firewall of your docker host
    # Set your build server to connect as build@<docker host> on port 9023
