#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
# Copyright (c) 2015 Mozilla Corporation
#
# Author: gdestuynder@mozilla.com

import os
from distutils.core import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "rra2json",
        py_modules = ['rra2json'],
        version = "2.0.0",
        author = "Guillaume Destuynder",
        author_email = "gdestuynder@mozilla.com",
        description = ("Converts Gsheet RRA documents to JSON and sends them to Mozilla's service-map"),
        license = "MPL",
        keywords = "google sheet gdocs drive json rra servicemap mozilla",
        url = "https://github.com/gdestuynder/rra2json",
        long_description = read('README.rst'),
        requires = [],
        classifiers = [
            "Development Status :: 5 - Production/Stable",
            "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        ],
)
