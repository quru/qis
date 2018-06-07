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
        "Pillow>=5.1.0,<6",
        "Flask==0.12.2",
        "pyldap==2.4.45",
        "pylibmc==1.5.2",
        "psycopg2==2.6.2",
        "SQLAlchemy==1.1.18",
        "requests==2.18.4",
        "psutil==5.4.1",
        "itsdangerous==0.24",
        "markdown==2.6.10"
    ],

    setup_requires=[
        "wheel",
        "nose"
    ],

    tests_require=[
        "coverage",
        "flake8"
    ],
)
