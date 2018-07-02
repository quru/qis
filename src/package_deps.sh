#!/bin/bash -e
#
# Script to pre-package all the Python dependencies for QIS
# (with C extensions compiled for the local platform).
# Creates an empty virtualenv, installs all requirements, then creates a
# tarball.gz of the resulting lib (incorporating site-packages) directory.
#
# Usage: src/package_deps.sh <python3 | python3.n>
#
# Outputs: $DIST_DIR/QIS-libs.tar.gz
#

PYTHON_BIN=$1
DIST_DIR=$(pwd)/dist
BUILD_DIR=$(pwd)/build
WHEELS_DIR=$BUILD_DIR/wheels
CACHE_DIR=$BUILD_DIR/cache
VENV_DIR=$BUILD_DIR/venv

if [ "$PYTHON_BIN" = "" ]; then
	echo "You must specify which python version to use, e.g. package_deps.sh python3.5"
	exit 1
fi

if ! [ -x "$(command -v $PYTHON_BIN)" ]; then
	echo "$PYTHON_BIN does not seem to be installed"
	exit 1
fi

echo -e '\nCleaning build environment'
rm -rf $BUILD_DIR

echo -e '\nCreating new build environment'
mkdir $BUILD_DIR
mkdir $WHEELS_DIR
mkdir $CACHE_DIR
virtualenv --python=$PYTHON_BIN $VENV_DIR
. $VENV_DIR/bin/activate

echo -e '\nUpgrading pip and setuptools'
pip install --upgrade pip setuptools wheel

# Download and cache the sdists for everything
echo -e '\nDownloading requirements'
pip download --dest $CACHE_DIR -r doc/requirements.txt

# Extract the sdists and build them into (bdist_wheel) wheels
echo -e '\nBuilding wheels of the requirements'
cd $CACHE_DIR
cp *.whl $WHEELS_DIR
find . -type f -name '*.zip' -exec unzip -o {} \;
find . -type f -name '*.tar.gz' -exec tar -zxf {} \;
find . -type f -name '*.tar.bz2' -exec tar -jxf {} \;
find . -type f -name 'setup.py' -execdir python -c "import setuptools; exec(open('setup.py').read(), {'__file__': './setup.py', '__name__': '__main__'})" bdist_wheel --dist-dir $WHEELS_DIR \;
cd ../..

# Install all the wheels we made (into the virtualenv's lib directory)
echo -e '\nInstalling all wheels into the build environment'
find $WHEELS_DIR -type f -name '*.whl' -exec wheel install --force {} \;

# Remove the pyc and pyo files
rm `find $VENV_DIR -name '*.py[co]'`

# Package the virtualenv's lib directory for distribution
echo -e '\nTarballing the virtualenv lib folder'
[ -d $DIST_DIR ] || mkdir $DIST_DIR
cd $BUILD_DIR
tar -C $VENV_DIR -czf $DIST_DIR/QIS-libs.tar.gz lib
