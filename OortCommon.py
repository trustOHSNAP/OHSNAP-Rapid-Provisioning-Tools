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


# Domain name validation code used in isDomainName() is derived from python-validators (https://github.com/python-validators/validators):
#
# python-validators License:
#
# The MIT License (MIT)
# 
# Copyright (c) 2013-2014 Konsta Vesterinen
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


#################
# OortCommon.py #
#################


# INTERNAL LIBRARIES
from OortArgs import OortArgs # must come first
import machdep
from machdep import machdepInit


# STANDARD LIBRARIES
import csv
import hashlib
from ipaddress import ip_address, IPv4Address
import json
import os
import platform
import re
import shutil
import socket
import string
import sys
import urllib.request


#
# CONSTANTS
#
CSV_COMMENT_START =          "#"
JSON_FILE_EXTENSION =        "json"
JSON_COMMENT_KEY =           "__COMMENT_FILENAME__"

### Configuration
CONFIG_FILE_BASE_NAME =      "CONFIG"
CONFIG_FILE_EXTENSION =      JSON_FILE_EXTENSION

CONFIG_DIR_ENV_VAR_NAME =   "OORTCONFIGDIR"
CONFIG_DIR_ALIAS_FILENAME = ".oortconfigpath"
CONFIG_DIR_DOT_DIRNAME =    ".oortconfig"

# Hardcoded config keys
CONFIG_KEY_CONFIGPATH =         "config-file-path"
CONFIG_KEY_EXECUTABLES_PATH =   "exec-dir"

# User-settable config keys
CONFIG_KEY_BUILD_ROOT_PATH =    "build-dir"
CONFIG_KEY_NETBOOT_INTERFACE =  "netboot-interface"
CONFIG_KEY_NETBOOT_HOST_IP =    "netboot-host-ip"
CONFIG_KEY_NETBOOT_TARGET_IP =  "netboot-target-ip"
CONFIG_KEY_NETBOOT_TARGET_MAC = "netboot-target-mac"

### Domains
DOMAIN_COMMON =              "common"
DOMAIN_REALM =               "realm"
DOMAIN_ROLE =                "role"
DOMAIN_BOARD =               "board"
DOMAIN_HOST =                "host"
# Override hierarchy (last one wins):  common -> realm -> role -> board -> host
DOMAINS = [DOMAIN_COMMON, DOMAIN_REALM, DOMAIN_ROLE, DOMAIN_BOARD, DOMAIN_HOST]

### Hostmap file
HOSTMAP_FILENAME =           "HOSTMAP.csv"
HOSTMAP_FIELD_HOSTNAME =     "HOSTNAME"
HOSTMAP_FIELD_REALM =        "REALM"
HOSTMAP_FIELD_ROLE =         "ROLE"
HOSTMAP_FIELD_OSFLAVOR =     "OSFLAVOR"
HOSTMAP_FIELD_BOARD =        "BOARD"
HOSTMAP_FIELD_ADMIN_IP =     "ADMIN_IP"
HOSTMAP_FIELD_MACADDR =      "MAC"
HOSTMAP_FIELD_OPTIONS_DICT = "options"

HOST_ROLE_VIRTUAL =          "VIRTUAL"

OSFLAVOR_STABLE =            "stable"
OSFLAVOR_CURRENT =           "current"

OPENBSD_CURRENT_DIRNAME =    "snapshots"
OPENBSD_PACKAGES_DIRNAME =   "packages"

#### Boardmap file
BOARDMAP_FILENAME =          "BOARDMAP.csv"
BOARDMAP_FIELD_BOARDNAME =   "BOARDNAME"
BOARDMAP_FIELD_SYSARCH =     "SYSARCH"
BOARDMAP_FIELD_PKGARCH =     "PKGARCH"
BOARDMAP_FIELD_BOOTLOADER_BOARDNAME = "BOOTLOADER_BOARD_NAME"
BOARDMAP_FIELD_BOOT_DEVICES = "INSTALL_BOOT_DEVICES"
BOARDMAP_FIELD_IMAGE_INFIX = "INSTALL_IMAGE_NAME_INFIX"
BOARDMAP_FIELD_FLASH_OPTIONS = "flashOptions" # not stored in BOARDMAP.csv; see _FLASHOPTIONS.json


#### Host options file
HOSTOPTIONS_KEY_DOMAIN_NAME = "domain-name"
HOSTOPTIONS_KEY_INSTALLURL  = "etc-install-url"


FLASHOPTIONS_FILENAME =      "_FLASHOPTIONS.json"
HOSTOPTIONS_FILENAME =       "_OPTIONS.json"

OPENBSD_VERSION_FILENAME =   "RELEASE.txt"

MACHDEP_DIRNAME =            "machdep"

NETBOOT_APACHE_CONFIG_FILENAME = "apache.conf"
NETBOOT_APACHE_PID_FILENAME = "apache.pid"
NETBOOT_APACHE_ACCESS_LOG_FILENAME = "apache_access.log"
NETBOOT_APACHE_ERROR_LOG_FILENAME = "apache_error.log"

SHA256_READ_CHUNK_SIZE =     1024 * 1024 # read a file in chunks of 1MB when computing SHA256 hash

#
# GLOBAL VARIABLES
#
# Persistent
gConfig = dict()
gLatestOpenBsdStableVersion = None
gVerboseLogs = True
gCsvCache = dict()
gBoardmap = None
gHostMap = None

#
# METHODS
#
def debug(s):
    global gVerboseLogs
    if gVerboseLogs:
        print(s)


def error(s):
     raise Exception(s)


def containsWhitespace(s):
    return True in [c in s for c in string.whitespace]
    
        
def replaceVariablesInString(text, varSubs):
    varSubs = dict((re.escape(k), v) for k, v in varSubs.items()) 
    pattern = re.compile("|".join(varSubs.keys()))
    return pattern.sub(lambda m: varSubs[re.escape(m.group(0))], text)
    

def makeDirIfNeeded(path):
    os.makedirs(path, exist_ok = True)
    

def assertNotRootUser():
    assert os.geteuid() > 0, "It is not safe to invoke this script as root. Re-run it as a normal user."

    
def sha256(path):
    debug("SHA256 %s..." % path)
    hasher = hashlib.sha256()
    with open(path,"rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(SHA256_READ_CHUNK_SIZE),b""):
            hasher.update(byte_block)
        sha256 = hasher.hexdigest()
    debug("... %s" % sha256)
    return sha256


def isIPv4(ip: str) -> bool:
    try:
        return True if type(ip_address(ip)) is IPv4Address else False
    except ValueError:
        return False


def isMAC(mac: str) -> bool:
    return re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", mac.lower())


def isDomainName(domain: str) -> bool:
    pattern = re.compile(
        r'^(([a-zA-Z]{1})|([a-zA-Z]{1}[a-zA-Z]{1})|'
        r'([a-zA-Z]{1}[0-9]{1})|([0-9]{1}[a-zA-Z]{1})|'
        r'([a-zA-Z0-9][-_.a-zA-Z0-9]{0,61}[a-zA-Z0-9]))\.'
        r'([a-zA-Z]{2,13}|[a-zA-Z0-9-]{2,30}.[a-zA-Z]{2,3})$'
    )
    return pattern.match(domain)


def loadCSV(relpath):
    global gCsvCache
    if not os.path.isfile(relpath):
        error("No file found at %s" % relpath)
    
    if relpath in gCsvCache:
        csvAsListOfDicts = gCsvCache[relpath]
    else:
        # skip empty lines and comments
        validCSV = list()
        with open(relpath) as rawfile:
            for line in rawfile:
                stripped_line = line.strip()
                if len(stripped_line) > 0 and not stripped_line.startswith(CSV_COMMENT_START):
                    validCSV.append(stripped_line)
        
        # use CSV parser to return a list of dictionaries
        csvAsListOfDicts = list()
        for rawRow in csv.DictReader(validCSV):
            # strip surrounding whitespace on keys & values
            row = dict()
            for k,v in rawRow.items():
                row[k.strip()] = v.strip()

            csvAsListOfDicts.append(row)

        gCsvCache[relpath] = csvAsListOfDicts
        
    return csvAsListOfDicts


def loadJSON(path):
    jsonDict = None
    with open(path, "r") as jsonFile:
        jsonDict = json.load(jsonFile)
    jsonDict.pop(JSON_COMMENT_KEY, None) # remove comment keys, if any
    return jsonDict 


def fetchOpenBSDVersion(flavor, architecture=None):
    """
    Fetch the current OpenBSD version from the official website.
    For stable: fetches from build Makefile
    For current: fetches from snapshots index.txt for the given architecture
    Returns the version number with period stripped (e.g., "77" for version 7.7).
    """
    if flavor == OSFLAVOR_STABLE:
        try:
            debug("Fetching OpenBSD stable version from https://www.openbsd.org/build/Makefile")
            with urllib.request.urlopen('https://www.openbsd.org/build/Makefile') as response:
                makefile_content = response.read().decode('utf-8')

            # Parse the STABLE_VERSION line
            for line in makefile_content.split('\n'):
                line = line.strip()
                if line.startswith('STABLE_VERSION='):
                    # Extract version number after the = sign
                    version = line.split('=')[1].strip()
                    # Remove tabs and any extra whitespace
                    version = version.replace('\t', '').strip()
                    # Remove the period to get format like "77" from "7.7"
                    version_no_period = version.replace('.', '')
                    debug("Found OpenBSD stable version: %s (formatted as %s)" % (version, version_no_period))
                    return version_no_period

            error("Could not find STABLE_VERSION in OpenBSD Makefile")
        except Exception as e:
            error("Failed to fetch OpenBSD stable version from website: %s" % str(e))

    elif flavor == OSFLAVOR_CURRENT:
        if architecture is None:
            error("Architecture is required for current flavor")

        try:
            snapshot_url = f"https://ftp.usa.openbsd.org/pub/OpenBSD/snapshots/{architecture}/index.txt"
            debug(f"Fetching OpenBSD current version from {snapshot_url}")
            with urllib.request.urlopen(snapshot_url) as response:
                index_content = response.read().decode('utf-8')

            # Parse the index.txt to find version information from base*.tgz files
            # Collect all version numbers in case there are multiple base files
            found_versions = []
            for line in index_content.split('\n'):
                line = line.strip()
                # Look for base files that contain version numbers like "base77.tgz"
                if line.endswith('.tgz') and 'base' in line:
                    # Extract version from filename like "base77.tgz"
                    version_match = re.search(r'base(\d{2,3})\.tgz', line)
                    if version_match:
                        version_no_period = version_match.group(1)
                        found_versions.append(int(version_no_period))
                        debug(f"Found OpenBSD current version candidate: {version_no_period}")

            if found_versions:
                # Return the highest version number found
                highest_version = str(max(found_versions))
                debug(f"Selected highest OpenBSD current version: {highest_version}")
                return highest_version

            error(f"Could not find version information in {snapshot_url}")
        except Exception as e:
            error(f"Failed to fetch OpenBSD current version from snapshots: {str(e)}")

    else:
        error(f"Unknown OpenBSD flavor '{flavor}'")


def openBSDVersion(hostdef):
    openBSDVersionForHost = None
    global gLatestOpenBsdStableVersion
    
    # Get the OS flavor and board architecture
    flavor = hostdef[HOSTMAP_FIELD_OSFLAVOR]
    boardname = hostdef[HOSTMAP_FIELD_BOARD]
    architecture = sysArchNameForBoard(boardname)
    
    if flavor == OSFLAVOR_STABLE:
        # For stable flavor, fetch the current stable version in real-time
        if gLatestOpenBsdStableVersion == None:
            gLatestOpenBsdStableVersion = fetchOpenBSDVersion(OSFLAVOR_STABLE)
        openBSDVersionForHost = gLatestOpenBsdStableVersion
    elif flavor == OSFLAVOR_CURRENT:
        # For current flavor, fetch the current version from snapshots
        openBSDVersionForHost = fetchOpenBSDVersion(OSFLAVOR_CURRENT, architecture)
    else:
        error("Unknown OpenBSD flavor '%s'" % flavor)
    
    return openBSDVersionForHost

    
def dottedVersion(undottedVersionString):
    return undottedVersionString[0] + '.' + undottedVersionString[1]


def copyFileIfNeeded(srcPath, dstPath):
    needsCopy = True

    if os.path.isfile(dstPath):
        if os.path.getsize(srcPath) == os.path.getsize(dstPath):
            if sha256(srcPath) == sha256(dstPath):
                needsCopy = False

    debug("Copy %s -> %s" % (srcPath, dstPath))            
    if needsCopy:
        shutil.copyfile(srcPath, dstPath)
    else:
        debug("  (Skipping)")


def getHostDefinition(hostname):    
    # find host in hostmap
    global gHostMap
    for hostdef in gHostMap:
        if hostdef[HOSTMAP_FIELD_HOSTNAME] == hostname:
            return hostdef
    return None
    

def getBoardConfiguration(boardname):
    global gBoardmap
    if gBoardmap is None:
        gBoardmap = dict()
        boardmapList = loadCSV(BOARDMAP_FILENAME)
        for boardEntry in boardmapList:
            boardName = boardEntry[BOARDMAP_FIELD_BOARDNAME]
            if boardName in gBoardmap:
                error("Board name '%s' has multiple entries in '%s'." % ( boardName, BOARDMAP_FILENAME))
            
            # Add image flash options fron board/_FLASHOPTIONS.json, if present
            flashOptionsFilePath = os.path.join(os.path.join(DOMAIN_BOARD, boardName), FLASHOPTIONS_FILENAME)
            if os.path.isfile(flashOptionsFilePath):
                with open(flashOptionsFilePath, "r") as flashOptionsFile:
                    boardEntry[BOARDMAP_FIELD_FLASH_OPTIONS] = json.load(flashOptionsFile)

            gBoardmap[boardName] = boardEntry

    return gBoardmap[boardname]


def sysArchNameForBoard(boardname):
    return getBoardConfiguration(boardname)[BOARDMAP_FIELD_SYSARCH]


def pkgArchNameForBoard(boardname):
    return getBoardConfiguration(boardname)[BOARDMAP_FIELD_PKGARCH]


def bootloaderBoardNameForBoard(boardname):
    return getBoardConfiguration(boardname)[BOARDMAP_FIELD_BOOTLOADER_BOARDNAME]


def installImageNameInfixForBoard(boardname):
    return getBoardConfiguration(boardname)[BOARDMAP_FIELD_IMAGE_INFIX]


def installImageFlashOptionsForBoard(boardname):
    installImageFlashOptions = None
    flashOptions = getBoardConfiguration(boardname).get(BOARDMAP_FIELD_FLASH_OPTIONS, None)
    if flashOptions:
        installImageFlashOptions = flashOptions['images']
    return installImageFlashOptions


def rootRelativePathForDomainResource(domain, hostdef, domainRelativePath):
    # strip a leading / so that os.path.join() doesn't incorrectly discard preceding path components
    if domainRelativePath.startswith('/'):
        domainRelativePath = domainRelativePath[1:]
    domainPathMapping = {
        DOMAIN_COMMON : os.path.join(DOMAIN_COMMON, domainRelativePath),
        DOMAIN_REALM  : os.path.join(DOMAIN_REALM,  hostdef[HOSTMAP_FIELD_REALM], domainRelativePath),
        DOMAIN_ROLE   : os.path.join(DOMAIN_ROLE,   hostdef[HOSTMAP_FIELD_ROLE], domainRelativePath),
        DOMAIN_BOARD  : os.path.join(DOMAIN_BOARD,  hostdef[HOSTMAP_FIELD_BOARD], domainRelativePath),
        DOMAIN_HOST   : os.path.join(DOMAIN_HOST,   hostdef[HOSTMAP_FIELD_HOSTNAME], domainRelativePath),
    }
    return domainPathMapping.get(domain, None)


def printHostConfigurationForDefinition(hostdef):
    board = hostdef[HOSTMAP_FIELD_BOARD]
    print("\n========= HOST CONFIGURATION =========")
    print("|        Hostname:  %s" % hostdef[HOSTMAP_FIELD_HOSTNAME])
    print("|            Role:  %s" % hostdef[HOSTMAP_FIELD_ROLE])
    print("|        Hardware:  %s (%s)" % (board, bootloaderBoardNameForBoard(board)))
    print("|  OpenBSD Flavor:  %s (%s / %s)" % (hostdef[HOSTMAP_FIELD_OSFLAVOR], sysArchNameForBoard(board), pkgArchNameForBoard(board)))
    print("|      IP Address:  %s" % hostdef[HOSTMAP_FIELD_ADMIN_IP])
    print("|     MAC Address:  %s" % hostdef[HOSTMAP_FIELD_MACADDR])
    print("|    Host Options:  %s" % hostdef[HOSTMAP_FIELD_OPTIONS_DICT])
    print("======================================\n")


def configValue(key):
    global gConfig
    return gConfig.get(key)


def locateConfigDirectory():    
    # Determine where the oort-config directory lives. The path can be specified in several ways.
    # Check in order of precedence:
    # 1. The -c / --config-dir command line argument
    # 2. The OORTCONFIGDIR environment variable
    # 3. An .oortconfigpath file in user's home directory, containing the path to oort-config
    # 4. An .oortconfig directory existing in the user's home directory containing the actual configuration
    debug("All CLI args: %r" % OortArgs().getArgs())

    # 1. The -c / --config-dir command line argument
    configDirPath = OortArgs().get('config_dir')
    debug("configDirPath = %r" % configDirPath)
    if configDirPath is not None:
        configDirPath = os.path.expanduser(configDirPath)
        assert os.path.isdir(configDirPath), configDirPath + " is not a valid oort-config directory path"
        return configDirPath

    # 2. The OORTCONFIGDIR environment variable
    configDirPath = os.getenv(CONFIG_DIR_ENV_VAR_NAME)
    if configDirPath is not None:
        configDirPath = os.path.expanduser(configDirPath)
        assert os.path.isdir(configDirPath), "The environment variable " + CONFIG_DIR_ENV_VAR_NAME + " does not contain a valid directory path"
        return configDirPath
        
    # 3. An .oortconfigpath file in user's home directory, containing the path to oort-config
    configDirPathAlias = os.path.expanduser(os.path.join("~", CONFIG_DIR_ALIAS_FILENAME))
    if os.path.isfile(configDirPathAlias):
        with open(configDirPathAlias, "r") as configDirPathAliasFile:
            configDirPath = configDirPathAliasFile.read().strip()
    if configDirPath is not None:
        assert os.path.isdir(configDirPath), "The file ~/" + CONFIG_DIR_ALIAS_FILENAME + " does not contain a valid directory path"
        return configDirPath
    
    # 4. An .oortconfig directory existing in the user's home directory containing the actual configuration
    configDirPath = os.path.expanduser(os.path.join("~", CONFIG_DIR_DOT_DIRNAME))
    if os.path.isdir(configDirPath):
        return configDirPath
    
    return None


def readConfigFile():
    global gConfig
    
    # Read global config file
    configFilename = CONFIG_FILE_BASE_NAME + '.' + CONFIG_FILE_EXTENSION
    configFilePath = os.path.abspath(configFilename)
    debug("Reading global config file %s" % configFilePath)
    assert os.path.isfile(configFilename), "No readable configuration file at " + configFilePath
    gConfig = loadJSON(configFilename)
    
    # Read host-local config file, if present
    localConfig = dict()
    localHostname = socket.gethostname()
    assert localHostname is not None and len(localHostname) > 0, "Couldn't determine local hostname"
    debug("Local hostname: %s" % localHostname)    
    configFilename = CONFIG_FILE_BASE_NAME + '-' + localHostname + '.' + CONFIG_FILE_EXTENSION
    if os.path.isfile(configFilename):
        debug("Reading local config file %s" % os.path.abspath(configFilename))
        localConfig = loadJSON(configFilename)

    # Merge configs
    gConfig = gConfig | localConfig
    debug("Merged config: %r" % gConfig)

    #
    # Set other global settings from config file
    #
    
    ### Configuration file path
    gConfig[CONFIG_KEY_CONFIGPATH] = configFilePath
    
    ### Build root path
    # Can be specified in config file(s) and/or overridden by -b / --build-dir command line argument
    buildRootPath = OortArgs().get('build_dir') or gConfig.get(CONFIG_KEY_BUILD_ROOT_PATH)
    assert buildRootPath is not None, "You must specify a build products directory via the -b / --build-dir argument or in the OORT configuration file ('build-dir' key)"
    buildRootPath = os.path.expanduser(buildRootPath)
    gConfig[CONFIG_KEY_BUILD_ROOT_PATH] = buildRootPath
    debug("Build Root Path:  %s" % buildRootPath)
    
    ### Executable path
    execPath = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
    gConfig[CONFIG_KEY_EXECUTABLES_PATH] = execPath
    debug("Executable Path:  %s" % execPath)


def validateHostmap():
    for d in gHostMap:
        hostname = d[HOSTMAP_FIELD_HOSTNAME]
        realm = d[HOSTMAP_FIELD_REALM]
        role = d[HOSTMAP_FIELD_ROLE]
        flavor = d[HOSTMAP_FIELD_OSFLAVOR]
        board = d[HOSTMAP_FIELD_BOARD]
        ip = d[HOSTMAP_FIELD_ADMIN_IP]
        mac = d[HOSTMAP_FIELD_MACADDR]
        assert(len(hostname) > 0 and not containsWhitespace(hostname))
        assert(   len(realm) > 0 and not containsWhitespace(realm))
        assert(    len(role) > 0 and not containsWhitespace(role))
        assert(  len(flavor) > 0 and not containsWhitespace(flavor))
        assert(      len(ip) > 0 and not containsWhitespace(ip) and isIPv4(ip))
        assert(     len(mac) > 0 and not containsWhitespace(mac) and isMAC(mac))


def loadHostOptions():
    for host in gHostMap:
        host[HOSTMAP_FIELD_OPTIONS_DICT] = dict()
        for domain in DOMAINS:
            hostOptionsFilepath = rootRelativePathForDomainResource(domain, host, HOSTOPTIONS_FILENAME)
            if os.path.isfile(hostOptionsFilepath):
                host[HOSTMAP_FIELD_OPTIONS_DICT].update(loadJSON(hostOptionsFilepath))


def hostOptionsValue(hostname, key, defaultValue = None):
    return next((host for host in gHostMap if host[HOSTMAP_FIELD_HOSTNAME] == hostname), dict()).get(HOSTMAP_FIELD_OPTIONS_DICT, dict()).get(key, defaultValue)


def getOperationalModeFromParsedArgs(args: dict):
    if args.list_hosts is True:
        return "list_hosts"
    
    return "default"


def listHostsAndExit():
    print("Available hosts:")
    
    for host in sorted(gHostMap, key=lambda x: x[HOSTMAP_FIELD_HOSTNAME]):
        if host[HOSTMAP_FIELD_ROLE] != HOST_ROLE_VIRTUAL:
            print("    %s" % host[HOSTMAP_FIELD_HOSTNAME])
    
    exit()


def OortInit(argParser: OortArgs):
    assert not platform.system() == 'Windows', "OORT is unsafe to run on Windows"

    assertNotRootUser()

    # Identify what OS we are running on and initialize the OS-specific layer
    machdepInit()
    
    # Find the oort-config directory
    configDirPath = locateConfigDirectory()
    assert configDirPath and os.path.isdir(configDirPath), "A valid oort-config directory could not be found. You must specify its absolute path via the -c/--config-dir argument, the " + CONFIG_DIR_ENV_VAR_NAME + " environment variable, or the ~/" + CONFIG_DIR_ALIAS_FILENAME + " file, or by storing your configuration in the ~/" + CONFIG_DIR_DOT_DIRNAME + " directory."

    # Change current directory to oort-config directory
    os.chdir(configDirPath)

    # Get user-configurable settings
    readConfigFile()

    # Load host definitions
    print("Loading host definitions...")
    global gHostMap
    gHostMap = loadCSV(HOSTMAP_FILENAME)
    validateHostmap()
    loadHostOptions()
    
    userOptions = argParser.getArgs()
    
    # Determine if we should run the tool as normal or perform another action instead
    mode = getOperationalModeFromParsedArgs(userOptions)    
    if mode == "default":
        pass
    elif mode == "list_hosts":
        listHostsAndExit()
    
    return userOptions
