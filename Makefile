PYTHON_VER := $(shell python -c 'import platform; print platform.python_version()[:3]')
PYTHON := python${PYTHON_VER}
VENV_NAME := qis_v2
VENV_PATH := ~/.virtualenvs/${VENV_NAME}
VENV_ACTIVATE := . ${VENV_PATH}/bin/activate
QISMAGICK_SO := ${VENV_PATH}/lib/${PYTHON}/site-packages/qismagick.so
QISMAGICK_WHEEL_PATH := /tmp/qismagick/

distribute:
	./package_deps.sh ${PYTHON}
	. build/venv/bin/activate ; python setup.py sdist
	echo 'Application and platform dependencies are now in the "dist" folder'

jenkins: test distribute

test:
	- make flake8.txt
	make test-unit

test-unit: venv
	${VENV_ACTIVATE} ; export LANG=en_GB.UTF-8 ; export LC_ALL=en_GB.UTF-8 ; python setup.py nosetests

runserver: venv
	${VENV_ACTIVATE} ; export LANG=en_GB.UTF-8 ; export LC_ALL=en_GB.UTF-8 ; python src/runserver.py 0.0.0.0

flake8.txt: venv ${VENV_PATH}/bin/flake8
	${VENV_ACTIVATE} ; flake8 src/ > flake8.txt || wc -l flake8.txt

${VENV_PATH}/bin/flake8: venv
	${VENV_ACTIVATE} ; pip install flake8

venv: ${VENV_PATH}/bin/activate doc/requirements.txt setup.py ${QISMAGICK_SO}
	test -d ${VENV_PATH} || virtualenv --python=${PYTHON} ${VENV_PATH}
	${VENV_ACTIVATE} ; pip install --upgrade pip ; pip install --upgrade setuptools
	${VENV_ACTIVATE} ; pip install --upgrade --force-reinstall --no-index --find-links file://$(QISMAGICK_WHEEL_PATH) qismagick
	${VENV_ACTIVATE} ; pip install -r doc/requirements.txt

.PHONY: venv test test-unit distribute runserver
