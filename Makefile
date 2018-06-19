PYTHON_BIN := $(shell which python3 || which python3.6 || which python3.5 || which python3.4)
PYTHON_VER := $(shell ${PYTHON_BIN} -c 'import platform; print(platform.python_version()[:3])')
PYTHON := python${PYTHON_VER}
VENV_PATH := .
VENV_ACTIVATE := . ${VENV_PATH}/bin/activate

export LANG=en_GB.UTF-8
export LC_ALL=en_GB.UTF-8

runserver: venv
	${VENV_ACTIVATE} ; python src/runserver.py

test: venv
	${VENV_ACTIVATE} ; python setup.py test

test_with_stats: venv testing_env
	make flake8.txt
	#coverage erase - doesn't seem to work with --parallel-mode
	rm -f .coverage*
	${VENV_ACTIVATE} ; coverage run --parallel-mode --source src/imageserver -m src.tests.junitxml -t src -s src/tests -o src/junit.xml
	coverage combine
	coverage xml -o src/coverage.xml
	coverage xml -o src/coverage.xml

distribute: venv webpack
	src/package_deps.sh ${PYTHON}
	${VENV_ACTIVATE} ; python setup.py sdist
	echo 'The packaged application and libraries are now in the "dist" folder'

jenkins: test_with_stats distribute

webpack:
	src/compress_js.sh

venv: ${VENV_PATH}/bin/activate setup.py doc/requirements.txt
	${VENV_ACTIVATE} ; pip install --upgrade pip setuptools wheel
	${VENV_ACTIVATE} ; pip install --upgrade -r doc/requirements.txt

testing_env: ${VENV_PATH}/bin/flake8 ${VENV_PATH}/bin/coverage

flake8.txt: testing_env
	${VENV_ACTIVATE} ; flake8 src > src/flake8.txt || wc -l src/flake8.txt

${VENV_PATH}/bin/flake8: ${VENV_PATH}/bin/activate
	${VENV_ACTIVATE} ; pip install flake8

${VENV_PATH}/bin/coverage: ${VENV_PATH}/bin/activate
	${VENV_ACTIVATE} ; pip install coverage

${VENV_PATH}/bin/activate:
	virtualenv --python=${PYTHON} ${VENV_PATH}

.PHONY: runserver test test_with_stats distribute jenkins webpack venv testing_env flake8.txt
