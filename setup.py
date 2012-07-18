#!/usr/bin/env python
from setuptools import setup, find_packages

install_requires = []

setup(
    name="storages",
    version="0.1dev1",

    description="",
    long_description=open("README.rst").read(),
    url="https://github.com/dstufft/storages",
    license=open("LICENSE").read(),

    author="Donald Stufft",
    author_email="donald.stufft@gmail.com",

    install_requires=install_requires,

    packages=find_packages(exclude=["tests"]),
    zip_safe=False,
)
