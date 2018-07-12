# QIS Cache server
#
# Runs memcached on Ubuntu 16.04.
#
# Environment variables:
#   MEMCACHED_SIZE - Optional - default 512
#
FROM ubuntu:16.04

LABEL maintainer="matt@quru.com" \
      description="QIS Memcached service"

# Base o/s + app layer
RUN apt-get update && \
    apt-get install -y apt-utils memcached && \
    apt-get clean

# Ports
EXPOSE 11211

# Runtime environment variables
ENV MEMCACHED_SIZE=512

# Add files to the image
COPY run-memcached.sh /
RUN chmod a+x /run-memcached.sh

# Note the "exec" form of CMD allows docker stop signals to be sent to our run script
CMD ["/run-memcached.sh"]
