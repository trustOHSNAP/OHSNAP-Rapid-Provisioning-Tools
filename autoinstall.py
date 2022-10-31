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


##################
# autoinstall.py #
##################

PROGRAM_DESCRIPTION = 'Run local BOOTP and HTTP servers to host netboot and/or set package downloads for automated installation on OpenBSD target system using autoinstall(8)'


# INTERNAL LIBRARIES
from OortArgs import OortArgs # must come first
from OortCommon import *
from machdep import *
from masterDisks import generateMasteringImageForHostname, prepareNetbootDirectories


# STANDARD LIBRARIES
import argparse
import asyncio
import os
import shlex
import shutil
import signal
import socket
import stat
import sys


#
# CONSTANTS
#

INDEX_FILENAME =        "index.html"
BOOTP_LEASES_FILENAME = "bootp.leases"
SPAWN_SCRIPT_FILENAME = "runnetboot.sh"

DNSMASQ_RELATIVE_PATH = os.path.join("machdep", "Darwin", "dnsmasq", "dnsmasq")

NETBOOT_FSROOT =             "netboot-filesystem-root"
NETBOOT_RUNTIME =            "netboot-runtime-dir"
NETBOOT_LEASES_FILE =        "netboot-bootp-leases"
NETBOOT_APACHE_CONFIG_FILE = "netboot-httpd-config"
NETBOOT_APACHE_PID_FILE =    "netboot-httpd-pid"
NETBOOT_APACHE_ERROR_FILE =  "netboot-httpd-errors"
NETBOOT_APACHE_ACCESS_FILE = "netboot-httpd-log"
NETBOOT_DNSMASQ_EXEC_PATH =  "netboot-dnsmasq-executable"


#
# CLASSES
#
class OpenBsdAutoInstaller:
    def __init__(self, hostdef):
        self.hostdef = hostdef
        self.s = dict() # settings for autoinstall process


    def runAutoinstallServer(self):
        self.s = self.getNetbootSettings()
        self.populateNetbootDirectory()
        self.spawnServerSubtasks()


    def getNetbootSettings(self):
        s = dict()

        configFilePath = configValue(CONFIG_KEY_CONFIGPATH)
        assert configFilePath is not None, "Configuration file path is missing from config"
        
        s[CONFIG_KEY_NETBOOT_INTERFACE] = configValue(CONFIG_KEY_NETBOOT_INTERFACE)
        assert s[CONFIG_KEY_NETBOOT_INTERFACE] is not None, "Configuration file %s is missing host network interface name for netboot (key: '%s')" % (configFilePath, CONFIG_KEY_NETBOOT_INTERFACE)
        assert any(s[CONFIG_KEY_NETBOOT_INTERFACE] in iface for iface in socket.if_nameindex()), "Network interface '%s' is not attached to the system. You may need to update your configuration file if the netboot interface has changed. (key: '%s')" % (s[CONFIG_KEY_NETBOOT_INTERFACE], CONFIG_KEY_NETBOOT_INTERFACE)  # make sure the specified network interface is found on the system

        s[CONFIG_KEY_NETBOOT_HOST_IP] = configValue(CONFIG_KEY_NETBOOT_HOST_IP)
        assert s[CONFIG_KEY_NETBOOT_HOST_IP] is not None and isIPv4(s[CONFIG_KEY_NETBOOT_HOST_IP]), "Configuration file %s has missing or invalid netboot host IP (key: '%s')" % (configFilePath, CONFIG_KEY_NETBOOT_HOST_IP)

        s[CONFIG_KEY_NETBOOT_TARGET_IP] = configValue(CONFIG_KEY_NETBOOT_TARGET_IP)
        assert s[CONFIG_KEY_NETBOOT_TARGET_IP] is not None and isIPv4(s[CONFIG_KEY_NETBOOT_TARGET_IP]), "Configuration file %s has missing or invalid netboot target IP (key: '%s')" % (configFilePath, CONFIG_KEY_NETBOOT_TARGET_IP)

        s[CONFIG_KEY_NETBOOT_TARGET_MAC] = self.hostdef[HOSTMAP_FIELD_MACADDR]
        assert s[CONFIG_KEY_NETBOOT_TARGET_MAC] is not None and isMAC(s[CONFIG_KEY_NETBOOT_TARGET_MAC]), "Hostmap has missing or invalid netboot target MAC ('%s' = %r)" % (HOSTMAP_FIELD_MACADDR, s[CONFIG_KEY_NETBOOT_TARGET_MAC])
        
        # NETBOOT_FSROOT and NETBOOT_RUNTIME will be added later by .populateNetbootDirectory()

        return s
        

    def populateNetbootDirectory(self):
        hostdef = self.hostdef
        hostname = hostdef[HOSTMAP_FIELD_HOSTNAME]

        # Run the OpenBSD mastering script to download and stage the set packages
        diskManifests = generateMasteringImageForHostname(hostname)
        setsManifest = diskManifests['sets_disk']
        
        # Create the netboot directory structure
        netbootDirectories = prepareNetbootDirectories(hostdef, BUILD_ROOT_PATH)
        netbootDirectories = prepareNetbootDirectories(hostdef, configValue(CONFIG_KEY_BUILD_ROOT_PATH))
        netbootHostDirectory = os.path.abspath(netbootDirectories['netboot_host'])
        
        # Update our settings
        self.s[NETBOOT_FSROOT] = os.path.abspath(netbootDirectories['netboot_root'])
        self.s[NETBOOT_RUNTIME] = os.path.abspath(netbootDirectories['netboot_runtime'])
        self.s[NETBOOT_DNSMASQ_EXEC_PATH] = os.path.join(configValue(CONFIG_KEY_EXECUTABLES_PATH), DNSMASQ_RELATIVE_PATH)
        self.s[NETBOOT_LEASES_FILE] = os.path.join(self.s[NETBOOT_RUNTIME], BOOTP_LEASES_FILENAME)
        self.s[NETBOOT_APACHE_CONFIG_FILE] = os.path.abspath(os.path.join(configValue(CONFIG_KEY_EXECUTABLES_PATH), MACHDEP_DIRNAME, machdep_platform(), NETBOOT_APACHE_CONFIG_FILENAME))
        self.s[NETBOOT_APACHE_PID_FILE] = os.path.join(self.s[NETBOOT_RUNTIME], NETBOOT_APACHE_PID_FILENAME)
        self.s[NETBOOT_APACHE_ERROR_FILE] = os.path.join(self.s[NETBOOT_RUNTIME], NETBOOT_APACHE_ERROR_LOG_FILENAME)
        self.s[NETBOOT_APACHE_ACCESS_FILE] = os.path.join(self.s[NETBOOT_RUNTIME], NETBOOT_APACHE_ACCESS_LOG_FILENAME)
        
        # Copy set packages from staging
        print("Copying set packages...")
        for setManifestEntry in setsManifest:
            src = setManifestEntry['abspath']
            dst = os.path.join(netbootHostDirectory, setManifestEntry['filename'])
            copyFileIfNeeded(src, dst)

        # Create an index.html file to identify the name of this host
        print("Writing %s..." % INDEX_FILENAME)
        indexFilePath = os.path.join(netbootHostDirectory, INDEX_FILENAME)
        with open(indexFilePath, 'w') as indexFile:
            indexFile.write(hostname)
    
        # Create empty Apache logs and bootp lease files as current user so that the sudo'd processes don't create them as root
        blankFilePaths = [
            self.s[NETBOOT_LEASES_FILE],
            self.s[NETBOOT_APACHE_ERROR_FILE],
            self.s[NETBOOT_APACHE_ACCESS_FILE]
        ]
        for fp in blankFilePaths:
            print("Writing %s..." % fp)
            with open(fp, 'w') as blankFile:
                blankFile.write('')


    def spawnServerSubtasks(self):
        dnsmasqPath = self.s[NETBOOT_DNSMASQ_EXEC_PATH]
        assert os.path.isfile(dnsmasqPath), "Missing Dnsmasq executable expected at %s" % dnsmasqPath

        hostname = self.hostdef[HOSTMAP_FIELD_HOSTNAME]

        # Build command invocations for BOOTP and HTTP servers
        bootpServerCmd = shlex.join([
            "./" + os.path.basename(dnsmasqPath),
            "--keep-in-foreground",
            "--interface=" + self.s[CONFIG_KEY_NETBOOT_INTERFACE],
            "--no-hosts",
            "--no-resolv",
            "--enable-tftp",
            "--tftp-root=" + self.s[NETBOOT_FSROOT],
            "--dhcp-leasefile=" + self.s[NETBOOT_LEASES_FILE],
            "--dhcp-range=" + self.s[CONFIG_KEY_NETBOOT_TARGET_IP] + ',' + self.s[CONFIG_KEY_NETBOOT_TARGET_IP],
            "--dhcp-host=" + self.s[CONFIG_KEY_NETBOOT_TARGET_MAC] + ',' + self.s[CONFIG_KEY_NETBOOT_TARGET_IP] + ',' + hostname + ',infinite',
            "--dhcp-boot=" + hostname + "/auto_install," + self.s[CONFIG_KEY_NETBOOT_HOST_IP],
            "--user=" + os.getlogin()
        ])
        httpServerCmd = shlex.join([
            "httpd",
            "-X", # keep in foreground
            "-d", self.s[NETBOOT_RUNTIME],
            "-f", self.s[NETBOOT_APACHE_CONFIG_FILE],
            "-E", self.s[NETBOOT_APACHE_ERROR_FILE],
            "-c", "PidFile " + self.s[NETBOOT_APACHE_PID_FILE],
            "-c", "ErrorLog " + self.s[NETBOOT_APACHE_ERROR_FILE],
            "-c", "CustomLog " + self.s[NETBOOT_APACHE_ACCESS_FILE] + " stdlogformat",
            "-c", "ServerName " + self.s[CONFIG_KEY_NETBOOT_HOST_IP],
            "-c", "User " + os.getlogin(),
            "-c", "DocumentRoot " + self.s[NETBOOT_FSROOT],
        ])
        
        # Create a master spawning-reaping script file to manage the server subtasks
        varSubs = { "$NETBOOT_RUNTIME_DIR": os.path.abspath(self.s[NETBOOT_RUNTIME]),
                    "$BOOTP_SERVER_CMD": bootpServerCmd,
                    "$HTTP_SERVER_CMD": httpServerCmd}
        spawnScript = replaceVariablesInString(
'''#!/bin/sh
#
# This is an autogenerated script. It is a build product
# of the OHSNAP OpenBSD Rapid Provisioning Tools project.
# (https://github.com/trustOHSNAP)
#
# Any modifications made here will be overwritten when
# the autoinstall tool is run.
#

exitCode=1

cleanup () {
    kill -TERM $PID1 $PID2 2> /dev/null
    exit $exitCode
}

cd "$NETBOOT_RUNTIME_DIR"

echo "Starting BOOTP server..."
$BOOTP_SERVER_CMD &
PID1="$!"

echo "Starting HTTP server..."
$HTTP_SERVER_CMD &
PID2="$!"

echo 
echo "The autoinstall server is now running. To start a fully automated installation of OpenBSD:"
echo 
echo "    1. Make sure that the target is attached to this machine with an Ethernet cable."
echo "    2. Boot the target into the OpenBSD installer. (You can use a boot disk generated by the OORT flashInstall tool.)"
echo "    3. If the autoinstall doesn't begin automatically, choose the '(A) autoinstall' option in the installer."
echo "    4. Wait until autoinstallation is complete and the target has rebooted."
echo
echo "Press [ENTER] when OpenBSD has finished installing and the target has been rebooted. (Exiting early may cause the installer to hang.)"

trap "exitCode=0; cleanup" INT
trap "cleanup" TERM EXIT

while true
do
    kill -0 $PID1 2> /dev/null
    if [ $? -ne 0 ]; then
        echo "dnsmasq terminated unexpectedly. Shutting down."
        exitCode=1
        cleanup
    fi

    kill -0 $PID2 2> /dev/null
    if [ $? -ne 0 ]; then
        echo "httpd terminated unexpectedly. Shutting down."
        exitCode=1
        cleanup
    fi

    read -t 1 dummy
    if [ $? -eq 0 ]; then
        echo "Cleaning up..."
        exitCode=0
        cleanup
    fi
done

''', varSubs)

        userRXMode = stat.S_IRUSR | stat.S_IXUSR
        
        spawnScriptPath = os.path.join(self.s[NETBOOT_RUNTIME], SPAWN_SCRIPT_FILENAME)
        # delete existing file since we can't overwrite it due to previously unset write permission
        if os.path.exists(spawnScriptPath):
            os.remove(spawnScriptPath)
        with open(spawnScriptPath, 'w') as spawnScriptFile:
            spawnScriptFile.write(spawnScript)
        os.chmod(spawnScriptPath, userRXMode)
        
        # Copy the dnsmasq binary to the local netboot runtime directory so that we can chroot() there
        src = dnsmasqPath
        dst = os.path.join(self.s[NETBOOT_RUNTIME], os.path.basename(dnsmasqPath))
        copyFileIfNeeded(src, dst)
        os.chmod(dst, userRXMode)
        
        # Re-read the script file we just wrote out just out of sheer paranoia
        with open(spawnScriptPath, 'r') as reopenedSpawnScriptFile:
            reopenedSpawnScript = reopenedSpawnScriptFile.read()
        assert reopenedSpawnScript == spawnScript, "Server master spawning script has been altered. Privilege escalation aborted."
        
        shouldSpawn = False
        print("\n\n*********************************************************************************************")
        print("*********************************************************************************************")
        print("*********************************************************************************************")
        print(reopenedSpawnScript)
        print("*********************************************************************************************")
        print("*********************************************************************************************")
        print("*********************************************************************************************")
        userInput = input("\n\n--> WARNING: You are about to run the above script with ROOT PRIVILEGES. Are you sure you want to do this? Type 'root' [ENTER] to continue or any other key to abort:  ")
        if userInput == "root":
            shouldSpawn = True
        else:
            print("Aborting.")
            exit()
        
        if shouldSpawn:
            print("Spinning up background tasks...")
            machdep_run_command_as_superuser([ spawnScriptPath ])


def main(argv):
    global PROGRAM_DESCRIPTION
    argParser = OortArgs(PROGRAM_DESCRIPTION)
    argParser.addArg("hostname", help="Name of host to be provisioned")
    args = OortInit(argParser)

    hostname = args.hostname

    # Load host definition
    hostdef = getHostDefinition(hostname)
    if hostdef is None:
        error("No host found with name '%s'" % hostname)

    # Print host configuration
    printHostConfigurationForDefinition(hostdef)
    
    print("Initiating autoinstall server setup...")
    ai = OpenBsdAutoInstaller(hostdef)
    ai.runAutoinstallServer()


if __name__ == "__main__":
    main(sys.argv[1:])
