PYTHON_VER := $(shell python -c 'import platform; print platform.python_version()[:3]')
PYTHON := python${PYTHON_VER}
VENV_PATH := .
VENV_ACTIVATE := . ${VENV_PATH}/bin/activate
QISMAGICK_SO := ${VENV_PATH}/lib/${PYTHON}/site-packages/qismagick.so
QISMAGICK_WHEEL_DIR := $$HOME/qis-build/qismagick
SET_LOCALE := export LANG=en_GB.UTF-8 ; export LC_ALL=en_GB.UTF-8

jenkins: test distribute

distribute: venv webpack
	src/package_deps.sh ${PYTHON}
	${VENV_ACTIVATE} ; python setup.py sdist
	echo 'The packaged application and libraries are now in the "dist" folder'

test:
	make flake8.txt
	make runtests

runtests: venv
	${VENV_ACTIVATE} ; ${SET_LOCALE} ; python setup.py nosetests

runserver: venv
	${VENV_ACTIVATE} ; ${SET_LOCALE} ; python src/runserver.py

webpack:
	src/compress_js.sh

flake8.txt: ${VENV_PATH}/bin/flake8
	${VENV_ACTIVATE} ; flake8 src/ > flake8.txt || wc -l src/flake8.txt

${VENV_PATH}/bin/flake8: venv
	${VENV_ACTIVATE} ; pip install flake8

venv: ${VENV_PATH}/bin/activate setup.py doc/requirements.txt ${QISMAGICK_SO}
ifeq (${PYTHON},python2.6)
	${VENV_ACTIVATE} ; pip install --upgrade "pip<10" "setuptools<37"
else
	${VENV_ACTIVATE} ; pip install --upgrade pip setuptools
endif
	${VENV_ACTIVATE} ; pip install --upgrade -r doc/requirements.txt

${QISMAGICK_SO}: setup.py doc/requirements.txt
	${VENV_ACTIVATE} ; pip install --upgrade --no-index --find-links file://$(QISMAGICK_WHEEL_DIR) qismagick

${VENV_PATH}/bin/activate:
	virtualenv --python=${PYTHON} ${VENV_PATH}

.PHONY: distribute jenkins test runtests runserver webpack venv
