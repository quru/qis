# QIS Application server
#
# RHEL build and testing environment.
#
FROM registry.access.redhat.com/rhel7:7.6 AS registered_system

# RH subscription variables. Pass these in as build arguments.
ARG RH_SUBS_USER
ARG RH_SUBS_PASSWORD

# Subscribe to RH updates before we can use yum
RUN subscription-manager register --username=$RH_SUBS_USER --password=$RH_SUBS_PASSWORD --auto-attach

# Update the system, ignoring the unusual repos
RUN yum update -y --disablerepo=*-eus-* --disablerepo=*-htb-* --disablerepo=*sjis* \
                  --disablerepo=*-ha-* --disablerepo=*-rt-* --disablerepo=*-lb-* \
                  --disablerepo=*-rs-* --disablerepo=*-sap-* && \
    yum clean all

# Disable the unusual repos
RUN yum-config-manager --disable *-eus-* *-htb-* *-ha-* *-rt-* *-lb-* \
                                 *-rs-* *-sap-* *-sjis-* > /dev/null

# Enable optional RPMs
RUN yum-config-manager --enable rhel-7-server-optional-rpms

# Install the EPEL and IUS repos
RUN yum -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-$(rpm -E '%{rhel}').noarch.rpm
RUN yum -y install https://rhel$(rpm -E '%{rhel}').iuscommunity.org/ius-release.rpm

# Start again with a standard build script
FROM registered_system

LABEL maintainer="matt@quru.com" \
      description="QIS build and test environment on Red Hat Enterprise Linux"

# Build variables
ARG BUILD_USER=build
ARG IM_VERSION=6.9.9-25
# This should contain a public key (the actual key, not a filename) that is
# allowed to log in via SSH. Pass this in as a build argument.
ARG AUTHORIZED_KEY

# Add extra o/s tools
RUN yum install -y sudo curl wget man git make gcc gcc-c++ sed mlocate tar zip unzip which \
                   java-1.8.0-openjdk-headless \
                   postgresql-devel openldap-devel openssl-devel libmemcached-devel \
                   python35u-devel python35u-pip \
                   openssh-server openssh-clients && \
    yum clean all
RUN pip3.5 install --upgrade pip setuptools wheel virtualenv

# Install ImageMagick devel from RPMs (as the RHEL 7 package is a buggy release)
RUN wget -P /tmp "https://quru.com/static2/imagemagick/ImageMagick-$IM_VERSION.x86_64.rpm" && \
    wget -P /tmp "https://quru.com/static2/imagemagick/ImageMagick-devel-$IM_VERSION.x86_64.rpm" && \
    wget -P /tmp "https://quru.com/static2/imagemagick/ImageMagick-libs-$IM_VERSION.x86_64.rpm"
RUN yum install -y /tmp/ImageMagick-libs-$IM_VERSION.x86_64.rpm && yum clean all
RUN yum install -y /tmp/ImageMagick-$IM_VERSION.x86_64.rpm && yum clean all
RUN yum install -y /tmp/ImageMagick-devel-$IM_VERSION.x86_64.rpm && yum clean all

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

# https://bugzilla.redhat.com/show_bug.cgi?id=1043212
RUN rm -f /run/nologin

# Run SSHD as the default command
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
