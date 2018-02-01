# QIS Application server
#
# Ubuntu build and testing environment.
#
FROM ubuntu:16.04

MAINTAINER Matt Fozard <matt@quru.com>

# Build variables
ARG BUILD_USER=build
# This should contain a public key (the actual key, not a filename) that is
# allowed to log in via SSH. Pass this in as a build argument.
ARG AUTHORIZED_KEY

# Add extra o/s tools
RUN apt-get update && \
    apt-get install -y apt-utils sudo curl wget pwgen tar zip unzip \
            vim man git make gcc python2.7 python2.7-dev \
            libldap2-dev libsasl2-dev libssl-dev \
            libpq-dev libmemcached-dev \
            openssl postgresql-client-9.5 \
            ghostscript imagemagick-6.q16 imagemagick-common libmagickwand-6.q16-dev \
            apache2 apache2-utils logrotate libapache2-mod-wsgi \
            python-letsencrypt-apache python-pip python-virtualenv && \
    apt-get clean

# Use latest Python tools
RUN pip install -U pip virtualenv

# Add libmagickwand env vars
ENV C_INCLUDE_PATH=/usr/include/x86_64-linux-gnu/ImageMagick-6:/usr/include/ImageMagick-6 \
    LIBRARY_PATH=/usr/lib/x86_64-linux-gnu \
    PATH=$PATH:/usr/lib/x86_64-linux-gnu/ImageMagick-6.8.9/bin-Q16

# Create a user for building and running stuff
RUN groupadd --gid 1001 $BUILD_USER && \
    useradd --uid 1001 --gid 1001 --groups sudo --create-home --shell /bin/bash $BUILD_USER
RUN sed -r -i 's/%sudo\s+ALL=\(ALL:ALL\)\s+ALL/%sudo    ALL=(ALL:ALL) ALL    NOPASSWD: ALL/g' /etc/sudoers

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
