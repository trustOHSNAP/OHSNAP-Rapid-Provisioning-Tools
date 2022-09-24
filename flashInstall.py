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


###################
# flashInstall.py #
###################


# INTERNAL LIBRARIES
from OortCommon import *
import masterDisks
from masterDisks import generateMasteringImageForHostname
from machdep import *


# STANDARD LIBRARIES
import argparse
import time
from typing import List, Union


#
# GLOBAL VARIABLES
#
#  Persistent:
gAutoAcceptYes = False


#
# CLASSES
#

# HumanBytes class copied from
# https://stackoverflow.com/questions/12523586/python-format-size-application-converting-b-to-kb-mb-gb-tb/63839503#63839503
# Explicit permission for use here given by original author: "I place this code in the public domain. Feel free to use it in your projects, both freeware and commercial."
class HumanBytes:
    METRIC_LABELS: List[str] = ["B", "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    BINARY_LABELS: List[str] = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"]
    PRECISION_OFFSETS: List[float] = [0.5, 0.05, 0.005, 0.0005] # PREDEFINED FOR SPEED.
    PRECISION_FORMATS: List[str] = ["{}{:.0f} {}", "{}{:.1f} {}", "{}{:.2f} {}", "{}{:.3f} {}"] # PREDEFINED FOR SPEED.

    @staticmethod
    def format(num: Union[int, float], metric: bool=False, precision: int=1) -> str:
        """
        Human-readable formatting of bytes, using binary (powers of 1024)
        or metric (powers of 1000) representation.
        """

        assert isinstance(num, (int, float)), "num must be an int or float"
        assert isinstance(metric, bool), "metric must be a bool"
        assert isinstance(precision, int) and precision >= 0 and precision <= 3, "precision must be an int (range 0-3)"

        unit_labels = HumanBytes.METRIC_LABELS if metric else HumanBytes.BINARY_LABELS
        last_label = unit_labels[-1]
        unit_step = 1000 if metric else 1024
        unit_step_thresh = unit_step - HumanBytes.PRECISION_OFFSETS[precision]

        is_negative = num < 0
        if is_negative: # Faster than ternary assignment or always running abs().
            num = abs(num)

        for unit in unit_labels:
            if num < unit_step_thresh:
                # VERY IMPORTANT:
                # Only accepts the CURRENT unit if we're BELOW the threshold where
                # float rounding behavior would place us into the NEXT unit: F.ex.
                # when rounding a float to 1 decimal, any number ">= 1023.95" will
                # be rounded to "1024.0". Obviously we don't want ugly output such
                # as "1024.0 KiB", since the proper term for that is "1.0 MiB".
                break
            if unit != last_label:
                # We only shrink the number if we HAVEN'T reached the last unit.
                # NOTE: These looped divisions accumulate floating point rounding
                # errors, but each new division pushes the rounding errors further
                # and further down in the decimals, so it doesn't matter at all.
                num /= unit_step

        return HumanBytes.PRECISION_FORMATS[precision].format("-" if is_negative else "", num, unit)


#
# METHODS
#
def selectRemovableDevice():
    chosenDeviceInfo = None
    devices = machdep_mounted_removable_devices()
    if len(devices) > 1:
        while chosenDeviceInfo is None:
            print("\n*** Select a removable device to ERASE and OVERWRITE with the OpenBSD installer image:")
            for idx, deviceInfo in enumerate(devices):
                name = deviceInfo['name']
                bsdNode = deviceInfo['node']
                size = deviceInfo['size']
                print('%i)  %s  (%s, %s)' % (idx+1, name, bsdNode, HumanBytes.format(size)))
            userInput = input("\nDevice to ERASE and OVERWRITE (1-%i or disk node): " % len(devices))

            if userInput.isnumeric():
                idx = int(userInput)
                if 1 <= idx <= len(devices):
                    chosenDeviceInfo = devices[idx-1]
                else:
                    print("Input must be in the range 1-%i." % len(devices))
            else:
                chosenDeviceInfo = next(filter(lambda deviceInfo: userInput == deviceInfo['node'], devices), None)
    elif len(devices) == 1:
        chosenDeviceInfo = devices[0]
    else:
        error("No removable devices found.")
    return chosenDeviceInfo
    

def confirmCommand(cmd):
    global gAutoAcceptYes
    if gAutoAcceptYes:
        return True
    userInput = input("%s   <-- Confirm command: [y/N] " % cmd)
    return userInput.lower() == 'y'
        

def runCommand(cmd: list, destructive=True, superuser=False):
    if superuser:
        commandPromptSymbol = '# '
    else:
        commandPromptSymbol = '$ '
        
    cmdString = ' '.join(cmd)
    if not destructive or confirmCommand(commandPromptSymbol + ' ' + cmdString):
        debug("Executing command:  %s %s" % (commandPromptSymbol, cmdString))
        if superuser:
            exitCode = machdep_run_command_as_superuser(cmd)
        else:
            exitCode = machdep_run_command(cmd)
        if exitCode != 0:
            error("%s '%s' exited with code %i (%s)" % (commandPromptSymbol, cmdString, exitCode, os.strerror(exitCode)))
    else:
        error("Aborting.")


def flashNode(nodeName, manifest):
    machdep_validate_disk_node(nodeName)
    print("Flashing %s..." % nodeName)
    flashCommands = list()
    debug("Preparing commands from manifest %r" % manifest)
    for imageInfo in manifest:
        imageName = imageInfo['filename']
        imagePath = imageInfo['abspath']
        assert not containsWhitespace(imagePath), "Absolute path ('%s') to image file '%s' must not contain any whitespace" % (imagePath, imageName)
        assert os.path.isabs(imagePath)
        assert os.path.isfile(imagePath)
        command = ['dd', 'if=%s' % imagePath, 'of=/dev/%s' % nodeName]
        if 'ddOptions' in imageInfo:
            for k,v in imageInfo['ddOptions'].items():
                assert not containsWhitespace(k)
                assert not containsWhitespace(v)
                command.append('%s=%s' % (k, v))

        debug("Adding command:  %r" % command)
        flashCommands.append(command)

    for command in flashCommands:
        machdep_unmount_disk(nodeName)
        runCommand(command, destructive=True, superuser=True)
        print("Waiting for disk to reappear...")
        time.sleep(5)

    print("Finished. %s is ready to install OpenBSD." % nodeName)
    input("\nPress Enter to eject %s...\n" % nodeName)
    machdep_unmount_disk(nodeName)
    

def eraseAndFlashNode(nodeName, diskManifest):
    machdep_erase_disk(nodeName)
    flashNode(nodeName, diskManifest)


def main(argv):
    assertNotRootUser()

    parser = argparse.ArgumentParser(description='Erase a removable storage device and write the OpenBSD installer image onto it.')
    parser.add_argument("hostname", help="Name of host for which to create the installer")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-accept confirmations to execute system commands")
    parser.add_argument("-v", "--verbosity", type=int, choices=[0, 1, 2], help="increase output verbosity")
    args = parser.parse_args()

    hostname = args.hostname
    global gAutoAcceptYes
    gAutoAcceptYes = args.yes

    # Load host definition
    hostdef = getHostDefinition(hostname)
    if hostdef is None:
        error("No host found with name '%s'" % hostname)

    # Print host configuration
    printHostConfigurationForDefinition(hostdef)
    
    # Run the OpenBSD mastering script to download and stage the installer image(s)
    diskManifests = generateMasteringImageForHostname(hostname)
    installerDiskManifest = diskManifests['installer_disk']

    # Erase and flash the installer boot disk (after selecting it, if necessary)
    device = selectRemovableDevice()
    assert device is not None, "No installation medium was chosen."
    print("*********************************************************************************************")
    print("***                                                                                       ***")
    print("***                    The device '%s' will be ERASED and all of                       ***" % device['node'])
    print("***                     the data on it will be PERMANENTLY DELETED.                       ***")
    print("***                                                                                       ***")
    print("***                            Name:  %s" % device['name'])
    print("***                     Mount Point:  /dev/%s" % device['node'])
    print("***                            Size:  %s" % HumanBytes.format(device['size']))
    print("***                                                                                       ***")
    print("*********************************************************************************************")
    
    if gAutoAcceptYes:
        print("\nWARNING: -y flag was specified -- all subsequent operations will proceed without confirmation")
        print("\n*********************************************************************************************")
    

    userInput = input("\n---> YOU ARE ABOUT TO ERASE %s. To continue, enter '%s' or press any other key to cancel: " % (device['node'], device['node']))
    
    if userInput == device['node']:
        eraseAndFlashNode(device['node'], installerDiskManifest)
    else:
        print("Aborted.")

if __name__ == "__main__":
    main(sys.argv[1:])
