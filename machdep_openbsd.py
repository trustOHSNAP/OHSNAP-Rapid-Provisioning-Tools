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


######################
# machdep_openbsd.py #
######################


from __future__ import annotations


# STANDARD LIBRARIES
import os
import signal
import subprocess

#
# Try to avoid import recursion
#
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from machdep import Machdep


#
# CLASSES
#
class OpenBSD:
    
    #
    # Public API
    #
    def __init__(self: Machdep):
        pass
        

    def run_command(self, cmd: list, superuser = False):
        exitCode = 0

        from OortCommon import debug

        debug("run_command(cmd = %r, superuser = %r)" % (cmd, superuser))

        if superuser:
            cmd.insert(0, 'doas')

        try:
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as cmd:
                for line in cmd.stdout:
                    print(line, end='')
        except KeyboardInterrupt:
            cmd.send_signal(signal.SIGINT)
    
        return cmd.returncode
