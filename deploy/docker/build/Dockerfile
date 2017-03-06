# QIS Application server
#
# Build and testing environment.
#
FROM quru/qis-as
MAINTAINER Matt Fozard <matt@quru.com>

# Add extra o/s tools
RUN apt-get install -y man git make gcc \
            python-dev libpq-dev libmagickwand-6.q16-dev && \
    apt-get clean

# Add libmagickwand env vars
ENV C_INCLUDE_PATH=/usr/include/x86_64-linux-gnu/ImageMagick-6:/usr/include/ImageMagick-6 \
    LIBRARY_PATH=/usr/lib/x86_64-linux-gnu \
    PATH=$PATH:/usr/lib/x86_64-linux-gnu/ImageMagick-6.8.9/bin-Q16

# Build variables
ARG QIS_USER=qis
ARG QIS_SRC_URL=https://github.com/quru/qis.git
ARG QIS_SRC_BRANCH=master

# Give the build user a normal home
USER root
RUN mkdir -p /home/$QIS_USER && \
    chown $QIS_USER:$QIS_USER /home/$QIS_USER && \
    usermod --home /home/$QIS_USER $QIS_USER

# Download the latest source code
USER $QIS_USER
WORKDIR /home/$QIS_USER
RUN git clone --depth=1 --branch=$QIS_SRC_BRANCH $QIS_SRC_URL qis-src

# Unset things we don't need
# TODO - EXPOSE and VOLUME - awaiting Docker support as of Docker v1.13, see https://github.com/docker/docker/issues/3465
HEALTHCHECK NONE

# Just run a shell as the default command
CMD ["/bin/bash"]
