#!/usr/bin/env python
from distutils.core import setup

version = "0.2.0"

setup(name="riemann-http-bridge",
      version=version,
      description="Python agent for proxying HTTP requests to Riemann",
      author="Brian Hatfield",
      author_email="bmhatfield@gmail.com",
      url="https://github.com/bmhatfield/riemann-http-bridge",
      data_files=[('/etc/init/', ["init/ubuntu/riemann-http-bridge.conf"])],
      scripts=["riemann-http-bridge.py"]
    )
