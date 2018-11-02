import os.path
from setuptools import setup, find_packages

package_dir = "src"

about = {}
with open(os.path.join(package_dir, "imageserver", "__about__.py")) as fp:
    exec(fp.read(), about)

setup(
    name=about["__tag__"],
    version=about["__version__"],
    description=about["__title__"] + ' - ' + about["__summary__"],
    long_description=about["__description__"],

    url=about["__uri__"],
    download_url=about["__source_uri__"],
    license=about["__license__"],
    platforms=about["__platforms__"],

    author=about["__author__"],
    author_email=about["__email__"],

    package_dir={"": package_dir},
    packages=find_packages(package_dir, exclude=["tests", "tests.*"]),
    test_suite="tests",

    install_requires=[
        "Pillow==5.2.0",
        "itsdangerous<1",
        "Flask==1.0.2",
        "python-ldap==3.1.0",
        "pylibmc==1.5.2",
        "psycopg2==2.7.5",
        "SQLAlchemy==1.2.8",
        "requests>=2.20,<3",
        "psutil==5.4.6",
        "markdown==2.6.11"
    ],

    setup_requires=[
        "wheel",
    ],

    tests_require=[
        "coverage",
        "flake8"
    ],
)
