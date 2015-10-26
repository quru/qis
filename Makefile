PYTHON := python2.6
VENV_NAME := qis_venv
VENV_PATH := ~/.virtualenvs/${VENV_NAME}
VENV_ACTIVATE := . ${VENV_PATH}/bin/activate
QISMAGICK_SO := ${VENV_PATH}/lib/${PYTHON}/site-packages/qismagick.so
QISMAGICK_WHEEL := $(wildcard /tmp/qismagick/*.whl)

distribute:
	./package_deps.sh ${PYTHON}
	. build/venv/bin/activate ; python setup.py sdist
	echo 'Application and platform dependencies are now in the "dist" folder'

jenkins: test distribute

test:
	- make flake8.txt
	make test-unit

test-unit: venv ${QISMAGICK_SO} setup.py
	${VENV_ACTIVATE} ; export LANG=en_GB.UTF-8 ; export LC_ALL=en_GB.UTF-8 ; python setup.py nosetests

flake8.txt: ${VENV_PATH}/bin/flake8 venv
	${VENV_ACTIVATE} ; flake8 src/ > flake8.txt || wc -l flake8.txt

${VENV_PATH}/bin/flake8: venv
	${VENV_ACTIVATE} ; pip install flake8

venv: ${VENV_PATH}/bin/activate

${VENV_PATH}/bin/activate: doc/requirements.txt
	test -d ${VENV_PATH} || virtualenv --python=${PYTHON} ${VENV_PATH}
	${VENV_ACTIVATE} ; pip install --upgrade pip ; pip install --upgrade setuptools
	${VENV_ACTIVATE} ; pip install -r doc/requirements.txt

${QISMAGICK_SO}:
	${VENV_ACTIVATE} ; pip install --upgrade --force-reinstall $(QISMAGICK_WHEEL)

runserver: venv ${QISMAGICK_SO}
	${VENV_ACTIVATE} ; export LANG=en_GB.UTF-8 ; export LC_ALL=en_GB.UTF-8 ; python src/runserver.py 0.0.0.0

.PHONY: test-unit flake8.txt distribute
