# QIS Application server
#
# CentOS build and testing environment.
#
FROM centos:7.4.1708

MAINTAINER Matt Fozard <matt@quru.com>

# Add extra o/s tools
RUN yum install -y sudo curl wget man git make gcc gcc-c++ sed mlocate \
                   postgresql-devel openldap-devel openssl-devel libmemcached-devel \
                   python-devel python-setuptools \
                   openssh-server openssh-clients && \
    yum clean all
RUN easy_install pip
RUN pip install wheel

# Build variables
ARG BUILD_USER=build
# This should contain a public key (the actual key, not a filename) that is
# allowed to log in via SSH. Pass this in as a build argument.
ARG AUTHORIZED_KEY

# Create a user for building and running stuff
RUN groupadd --gid 1001 $BUILD_USER && \
    useradd --uid 1001 --gid 1001 --groups wheel --create-home --shell /bin/bash $BUILD_USER
RUN sed -r -i 's/%wheel\s+ALL=\(ALL\)\s+ALL/%wheel        ALL=(ALL)       NOPASSWD: ALL/g' /etc/sudoers

# Install an authorized key for logging in as the build user
USER $BUILD_USER
WORKDIR /home/$BUILD_USER
RUN mkdir .ssh && chmod 700 .ssh
RUN echo "$AUTHORIZED_KEY" > .ssh/authorized_keys && \
    chmod 600 .ssh/authorized_keys

# Set up SSHD
USER root
RUN ssh-keygen -A

# Run SSHD as the default command
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
