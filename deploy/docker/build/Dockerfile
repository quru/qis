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

# Unset things we don't need
# TODO - EXPOSE and VOLUME - awaiting Docker support as of Docker v1.13, see https://github.com/docker/docker/issues/3465
HEALTHCHECK NONE

# Just run a shell as root
USER root
CMD ["/bin/bash"]
