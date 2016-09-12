import os.path
from setuptools import setup, find_packages

package_dir = "src/"

about = {}
with open(os.path.join(package_dir, "imageserver/__about__.py")) as fp:
    exec(fp.read(), about)

setup(
    name=about["__title__"],
    version=about["__version__"],

    description=about["__summary__"],
    long_description=about["__description__"],
    license=about["__license__"],
    url=about["__uri__"],
    download_url=about["__source_uri__"],
    platforms=about["__platforms__"],

    author=about["__author__"],
    author_email=about["__email__"],

    package_dir={"": package_dir},
    packages=find_packages(package_dir, exclude=["tests", "tests.*"]),

    install_requires=[
        "qismagick>=2.0.0",
        "Flask==0.10.1",
        "python-ldap==2.4.27",
        "pylibmc==1.5.1",
        "psycopg2==2.6.2",
        "SQLAlchemy==1.0.15",
        "requests==2.11.1",
        "psutil==2.2.1",
        "itsdangerous==0.24",
        "importlib",  # Only for Python 2.6
        "markdown==2.6.6"
    ],

    setup_requires=[
        "wheel",
        "nose"
    ],

    tests_require=[
        "unittest2",
        "mock",
        "coverage"
    ],
)
