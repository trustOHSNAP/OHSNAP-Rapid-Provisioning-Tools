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


#####################
# machdep_darwin.py #
#####################


from __future__ import annotations


# STANDARD LIBRARIES
import os
import shlex

#
# Try to avoid import recursion
#
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from machdep import Machdep


#
# CLASSES
#
class Darwin:

    #
    # Public API
    #
    def __init__(self: Machdep):
        pass
            
    def run_command_as_superuser(self, cmd):
        exitCode = 0

        rawSystemCommandComponents = [
            "osascript",
            "-e",
            "do shell script %s "
            "with administrator privileges "
            "without altering line endings"
            % Darwin.quote_applescript(shlex.quote(cmd))
        ]

        rawSystemCommand = shlex.join(rawSystemCommandComponents)

        from OortCommon import debug
        debug("rawSystemCommand = %s" % rawSystemCommand)

        exitCode = os.system(rawSystemCommand)
    
        return exitCode


    def mounted_removable_devices(self):
        import iokitBridge
        from iokitBridge import iokitGetMountedRemovableDevices
        return iokitGetMountedRemovableDevices()

    #
    # Private API
    #
    @staticmethod 
    def quote_applescript(string):
        charmap = {
            "\n": "\\n",
            "\r": "\\r",
            "\t": "\\t",
            "\"": "\\\"",
            "\\": "\\\\",
        }
        return '"%s"' % "".join(charmap.get(char, char) for char in string)