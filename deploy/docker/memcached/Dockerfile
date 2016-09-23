# QIS Cache server
#
# Runs memcached on Ubuntu 16.04.
#
# Environment variables:
#   MEMCACHED_SIZE - Optional - default 512
#
FROM ubuntu:16.04
MAINTAINER Matt Fozard <matt@quru.com>

# Base o/s layer
RUN apt-get update && apt-get upgrade && apt-get clean

# App layer
RUN apt-get install -y memcached && apt-get clean

# Ports
EXPOSE 11211

# Environment variables
ENV MEMCACHED_SIZE 512

# Command
CMD /usr/bin/memcached -u memcache -m $MEMCACHED_SIZE
