# QIS Database server
#
# Runs a pre-configured instance of PostgreSQL on Ubuntu 16.04.
#
# Environment variables:
#   PG_USER - Optional - the QIS database login username
#   PG_PASSWORD - Required - the QIS database login password
#   PG_MAX_CONNECTIONS - Optional - the Postgres connection limit
#   PG_SHARED_BUFFERS - Optional - the Postgres internal cache size
#   PG_EFFECTIVE_CACHE_SIZE - Optional - the expected o/s free memory + buffers total
#   PGDATA - Optional - the path at which to create the QIS database
#
FROM ubuntu:16.04

LABEL maintainer="matt@quru.com" \
      description="QIS Postgres service"

# Base o/s + app layer
RUN apt-get update && \
    apt-get install -y apt-utils postgresql-9.5 && \
    apt-get clean
RUN locale-gen en_GB.UTF-8 && update-locale LANG=en_GB.UTF-8 LC_ALL=en_GB.UTF-8

# Ports
EXPOSE 5432

# Runtime environment variables
ENV PG_USER=qis \
    PG_PASSWORD=qispass \
    PG_MAX_CONNECTIONS=100 \
    PG_SHARED_BUFFERS=250MB \
    PG_EFFECTIVE_CACHE_SIZE=750MB

# Software-specific environment variables
ENV PGDATA=/opt/qis/data

# Add files to the image
COPY *.sh /
RUN chmod a+x /*.sh

# Create PGDATA
RUN mkdir -p $PGDATA && chown postgres:postgres $PGDATA

USER postgres

# Declare data volumes
VOLUME $PGDATA

# Run regular health checks
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD ["/check-postgres.sh"]

# Note the "exec" form of CMD allows docker stop signals to be sent to our run script
CMD ["/run-postgres.sh"]
