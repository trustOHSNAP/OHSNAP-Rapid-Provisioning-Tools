#!python3
# For Python 3.9.10 or later

# ISC License
# 
# Copyright (c) 2022 OHSNAP
# 
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
# 
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
# INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
# LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
# OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
# PERFORMANCE OF THIS SOFTWARE.


###############
# OortArgs.py #
###############


# STANDARD LIBRARIES
import argparse
import pathlib

#
# Public API
#
def OortArgs(programDescription: str = None):
    global gOortArgParser
    if gOortArgParser is None:
        gOortArgParser = OortArgParser(programDescription)
    return gOortArgParser


#
# Private API
#
gOortArgParser = None


class OortArgParser:

    parser = None
    description = None
    userArgs = None
    
    def __init__(self, programDescription: str = None):
        if programDescription is not None:
            self.description = programDescription
        self.parser = argparse.ArgumentParser(description=self.description)
        self.parser.add_argument("-v", "--verbosity", type=int, choices=[0, 1, 2], help="increase output verbosity")
        self.parser.add_argument("-c", "--config-dir", type=pathlib.Path, help="path to oort-config (configuration files) directory")
        self.parser.add_argument("-b", "--build-dir", type=pathlib.Path, help="path to oort-build (build products) directory")
        
        operationGroup = self.parser.add_mutually_exclusive_group()
        operationGroup.add_argument("-d", "--default-operation", action='store_true', default=False, help="run this tool normally (this is the default)")
        operationGroup.add_argument("-l", "--list-hosts", action='store_true', default=False, help="instead of running this tool, list all defined hostnames and exit")


    def getArgs(self):
        return self.parser.parse_args()


    def get(self, key):
        return getattr(self.getArgs(), key, None)

    
    def addArg(self, *args, **kwargs):
        self.parser.add_argument(*args, **kwargs)
