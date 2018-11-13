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
VENV_DIR=$BUILD_DIR/venv

if [ "$PYTHON_BIN" = "" ]; then
	echo "You must specify which python version to use, e.g. package_deps.sh python3.5"
	exit 1
fi

if ! [ -x "$(command -v $PYTHON_BIN)" ]; then
	echo "$PYTHON_BIN does not seem to be installed"
	exit 1
fi

echo -e '\nCreating new build environment'
rm -rf $BUILD_DIR
mkdir $BUILD_DIR
virtualenv --python=$PYTHON_BIN $VENV_DIR
. $VENV_DIR/bin/activate

echo -e '\nUpgrading pip and setuptools'
pip install --upgrade pip setuptools

echo -e '\nInstalling requirements'
pip install --upgrade -r doc/requirements.txt

echo -e '\nRemoving pyc and pyo files'
rm `find $VENV_DIR -name '*.py[co]'`

# Package the virtualenv's lib directory for distribution
echo -e '\nTarballing the virtualenv lib folder'
[ -d $DIST_DIR ] || mkdir $DIST_DIR
cd $BUILD_DIR
tar -C $VENV_DIR -czf $DIST_DIR/QIS-libs.tar.gz lib
