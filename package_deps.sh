#!/bin/bash -e
#
# Script to pre-package all the Python dependencies for QIS
# (with C extensions compiled for the local platform).
# Creates an empty virtualenv, installs all requirements, then creates a
# tarball.gz of the resulting lib/python2.x/site-packages directory.
#
# Usage: package_deps.sh <python2.6 | python2.7>
#
# Outputs: $DIST_DIR/dependencies.tar.gz
#

PYTHON_VER=$1
VENV=venv
DIST_DIR=$(pwd)/dist
BUILD_DIR=$(pwd)/build
WHEELS_DIR=$BUILD_DIR/wheels
CACHE_DIR=$BUILD_DIR/cache

if [ "$PYTHON_VER" = "" ]; then
	echo "You must specify which python version to use, e.g. package_deps.sh python2.7"
	exit 1
fi

if ! [ -x "$(command -v $PYTHON_VER)" ]; then
	echo "$PYTHON_VER does not seem to be installed"
	exit 1
fi

echo -e '\nCleaning build environment'
rm -rf $BUILD_DIR

echo -e '\nCreating new build environment'
mkdir $BUILD_DIR
mkdir $WHEELS_DIR
mkdir $CACHE_DIR
cd $BUILD_DIR
virtualenv --python=$PYTHON_VER $VENV
. $VENV/bin/activate
cd ..

# Upgrade the venv to avoid setuptools bugs
echo -e '\nUpgrading pip and setuptools'
pip install -U pip
pip install -U setuptools
pip install wheel

# Download and cache the sdists for everything
echo -e '\nDownloading requirements'
pip install --download $CACHE_DIR -r doc/requirements.txt

# Extract the sdists and build them into (bdist_wheel) wheels
echo -e '\nBuilding wheels of the requirements'
cd $CACHE_DIR
cp *.whl $WHEELS_DIR
find . -type f -name '*.zip' -exec unzip -o {} \;
find . -type f -name '*.tar.gz' -exec tar -zxf {} \;
find . -type f -name '*.tar.bz2' -exec tar -jxf {} \;
find . -type f -name 'setup.py' -execdir python -c "import setuptools; execfile('setup.py', {'__file__': './setup.py', '__name__': '__main__'})" bdist_wheel --dist-dir $WHEELS_DIR \;
cd ../..

# Add in the qismagick wheel, if present
echo -e '\nAdding qismagick.so wheel'
[ -d /tmp/qismagick ] && cp /tmp/qismagick/*.whl $WHEELS_DIR
[ -d /tmp/qismagick ] || echo 'WARNING! /tmp/qismagick/*.whl not found (you will need to add it later)'

# Install all the wheels we made (into the virtualenv's lib directory)
echo -e '\nInstalling all wheels into the build environment'
find $WHEELS_DIR -type f -name '*.whl' -exec wheel install --force {} \;

# Package the virtualenv's lib directory for distribution
echo -e '\nTarballing the lib/python2.x/site-packages folder'
[ -d $DIST_DIR ] || mkdir $DIST_DIR
cd $BUILD_DIR
tar -C $VENV/lib/$PYTHON_VER -czf $DIST_DIR/dependencies.tar.gz site-packages
