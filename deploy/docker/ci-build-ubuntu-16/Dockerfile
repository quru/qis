# QIS Application server
#
# Ubuntu build and testing environment.
#
FROM ubuntu:16.04

LABEL maintainer="matt@quru.com" \
      description="QIS build and test environment on Ubuntu"

# Build variables
ARG BUILD_USER=build
# This should contain a public key (the actual key, not a filename) that is
# allowed to log in via SSH. Pass this in as a build argument.
ARG AUTHORIZED_KEY

# Add extra o/s tools
RUN apt-get update && \
    apt-get install -y apt-utils sudo curl wget pwgen tar zip unzip \
            vim man git make gcc g++ \
            openjdk-8-jre-headless \
            libldap2-dev libssl-dev \
            libpq-dev libmemcached-dev \
            openssl postgresql-client-9.5 \
            ghostscript imagemagick-6.q16 imagemagick-common libmagickwand-6.q16-dev \
            apache2 apache2-utils logrotate libapache2-mod-wsgi-py3 \
            python3-dev python3-pip \
            openssh-server && \
    apt-get clean

# Use latest Python tools
RUN pip3 install --upgrade pip setuptools wheel virtualenv

# Add libmagickwand env vars
RUN echo "export C_INCLUDE_PATH=$C_INCLUDE_PATH:/usr/include/x86_64-linux-gnu/ImageMagick-6:/usr/include/ImageMagick-6" >> /etc/profile.d/libmagickwand-dev.sh
RUN echo "export LIBRARY_PATH=$LIBRARY_PATH:/usr/lib/x86_64-linux-gnu" >> /etc/profile.d/libmagickwand-dev.sh
RUN echo "export PATH=$PATH:/usr/lib/x86_64-linux-gnu/ImageMagick-6.8.9/bin-Q16" >> /etc/profile.d/libmagickwand-dev.sh
RUN chmod a+x /etc/profile.d/libmagickwand-dev.sh

# Create a user for building and running stuff
RUN groupadd --gid 1001 $BUILD_USER && \
    useradd --uid 1001 --gid 1001 --groups sudo --create-home --shell /bin/bash $BUILD_USER
RUN sed -r -i 's/%sudo\s+ALL=\(ALL:ALL\)\s+ALL/%sudo  ALL=(ALL:ALL)  NOPASSWD: ALL/g' /etc/sudoers

# Install an authorized key for logging in as the build user
USER $BUILD_USER
WORKDIR /home/$BUILD_USER
RUN mkdir .ssh && chmod 700 .ssh
RUN echo "$AUTHORIZED_KEY" > .ssh/authorized_keys && \
    chmod 600 .ssh/authorized_keys

# Set up SSHD
USER root
RUN ssh-keygen -A

# https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=864190
RUN mkdir -p /var/run/sshd

# Run SSHD as the default command
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
