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


##############
# machdep.py #
##############


#
# Try to avoid import recursion
#
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from machdep_darwin import Darwin
    from machdep_openbsd import OpenBSD


#
# PUBLIC API
#

def machdepInit():
    machdep()

def machdep_run_command(cmd: list):
    return machdep().run_command(cmd)

def machdep_run_command_as_superuser(cmd: list):
    return machdep().run_command(cmd, superuser=True)

def machdep_mounted_removable_devices():
    return machdep().mounted_removable_devices()

def machdep_unmount_disk(nodeName):
    return machdep().unmount_disk(nodeName)

def machdep_erase_disk(nodeName):
    return machdep().erase_disk(nodeName)

def machdep_validate_disk_node(nodeName):
    return machdep().validate_disk_node(nodeName)


#
# PRIVATE API
#

import os

from machdep_darwin import Darwin
from machdep_openbsd import OpenBSD

gMachdep = None

class Machdep(object):

    def run_command(self, cmd: list, superuser = False):
        raise NotImplementedError()

    def mounted_removable_devices(self):
        raise NotImplementedError()

    def unmount_disk(self, nodeName):
        raise NotImplementedError()

    def erase_disk(self, nodeName):
        raise NotImplementedError()

    def validate_disk_node(self, nodeName):
        raise NotImplementedError()

    
def GetMachindDependentClassName():
    osName = os.uname().sysname
    if osName == "Darwin":
        return Darwin
    elif osName == "OpenBSD":
        return OpenBSD
    else:
        error("The %s operating system is not currently supported." % osName)


def machdep():
    global gMachdep
    if gMachdep is None:
        className = GetMachindDependentClassName()
        gMachdep = className()
    return gMachdep
