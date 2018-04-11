# QIS Application server
#
# Runs a pre-configured instance of Apache+QIS on Ubuntu 16.04.
# Requires qis-postgres and qis-memcached containers at runtime.
#
# Environment variables:
#   HOSTNAME - Required - the host name for Apache to listen on
#   DB_USER - Required - the database username
#   DB_PASSWORD - Required - the database password
#
#   HTTP_PROCESSES - Optional - set the number of mod_wsgi processes for HTTP
#   HTTP_THREADS - Optional - set the number of mod_wsgi threads per process for HTTP
#   HTTPS_PROCESSES - Optional - set the number of mod_wsgi processes for HTTPS
#   HTTPS_THREADS - Optional - set the number of mod_wsgi threads per process for HTTPS
#
FROM ubuntu:16.04
MAINTAINER Matt Fozard <matt@quru.com>

# Base o/s + app layer
RUN apt-get update && \
    apt-get install -y apt-utils curl wget pwgen tar zip unzip vim \
            python-dev libldap2-dev libsasl2-dev libssl-dev \
            libpq-dev libmemcached-dev \
            openssl postgresql-client-9.5 \
            python2.7 ghostscript imagemagick-6.q16 imagemagick-common \
            apache2 apache2-utils logrotate libapache2-mod-wsgi \
            python-letsencrypt-apache python-pip python-virtualenv && \
    apt-get clean
RUN locale-gen en_GB.UTF-8 && update-locale LANG=en_GB.UTF-8 LC_ALL=en_GB.UTF-8

# Use latest Python tools
RUN pip install -U pip virtualenv

# Build variables
ARG QIS_VERSION=3.0.0
ARG QIS_USER=qis
ARG QIS_INSTALL_DIR=/opt/qis
ARG WEB_USER=www-data
ARG PYTHON_VERSION=python2.7

# Ports
EXPOSE 80 443

# Runtime environment variables
ENV HOSTNAME=images.example.com \
    DB_USER=qis \
    DB_PASSWORD=qispass \
    QIS_HOME=$QIS_INSTALL_DIR \
    HTTP_USER=$QIS_USER \
    HTTP_PROCESSES=2 \
    HTTP_THREADS=15 \
    HTTPS_PROCESSES=2 \
    HTTPS_THREADS=15

# Create the application user
RUN useradd --comment "Quru Image Server" --groups $WEB_USER --home $QIS_INSTALL_DIR --system --shell /sbin/nologin $QIS_USER

# Create the app dir
RUN mkdir -p $QIS_INSTALL_DIR

# Install scripts
COPY *.sh /
RUN chmod a+x /*.sh

# Download and install QIS files
RUN cd /tmp && \
    curl -L "https://github.com/quru/qis/archive/v$QIS_VERSION.tar.gz" -o qis.tar.gz && \
    tar -zxvf qis.tar.gz && \
    cd qis-$QIS_VERSION && \
    cp LICENSE README.md $QIS_INSTALL_DIR && \
    cp -r conf $QIS_INSTALL_DIR && \
    cp -r doc $QIS_INSTALL_DIR && \
    cp -r icc $QIS_INSTALL_DIR && \
    cp -r images $QIS_INSTALL_DIR && \
    cp -r licences $QIS_INSTALL_DIR && \
    cp -r logs $QIS_INSTALL_DIR && \
    rm -rf src/tests src/*.sh src/runserver.py && \
    cp -r src $QIS_INSTALL_DIR && \
    cp deploy/ubuntu16/wsgi.conf /etc/apache2/sites-available/qis-wsgi.conf && \
    cp deploy/ubuntu16/httpd.conf.sample /etc/apache2/sites-available/001-qis.conf && \
    cp deploy/ubuntu16/httpd-ssl.conf.sample /etc/apache2/sites-available/002-qis-ssl.conf && \
    cd - && \
    rm -rf /tmp/* && \
    chown -R $QIS_USER:$QIS_USER $QIS_INSTALL_DIR

# Download and install Python libs
USER $QIS_USER
WORKDIR $QIS_INSTALL_DIR
RUN virtualenv --python=$PYTHON_VERSION . && \
    rm -rf local && \
    . bin/activate && \
    pip install --no-cache-dir -r doc/requirements.txt

# TODO Install qismagick package

# Configure Apache
USER root
RUN ln -s /etc/apache2/mods-available/ssl.load /etc/apache2/mods-enabled/ssl.load && \
    ln -s /etc/apache2/mods-available/ssl.conf /etc/apache2/mods-enabled/ssl.conf && \
    ln -s /etc/apache2/mods-available/socache_shmcb.load /etc/apache2/mods-enabled/socache_shmcb.load && \
    ln -s /etc/apache2/mods-available/expires.load /etc/apache2/mods-enabled/expires.load && \
    rm /etc/apache2/sites-enabled/000-default.conf && \
    ln -s /etc/apache2/sites-available/qis-wsgi.conf /etc/apache2/sites-enabled/qis-wsgi.conf && \
    ln -s /etc/apache2/sites-available/001-qis.conf /etc/apache2/sites-enabled/001-qis.conf && \
    ln -s /etc/apache2/sites-available/002-qis-ssl.conf /etc/apache2/sites-enabled/002-qis-ssl.conf

# Persistent storage volumes
VOLUME ["$QIS_INSTALL_DIR/images", "$QIS_INSTALL_DIR/logs", "/var/log/apache2"]

# Run regular health checks
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD ["/check-qis.sh"]

# Note the "exec" form of CMD allows docker stop signals to be sent to our run script
CMD ["/run-qis.sh"]
