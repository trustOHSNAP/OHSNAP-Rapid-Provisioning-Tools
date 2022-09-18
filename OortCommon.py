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


#
# CONSTANTS
#
CSV_COMMENT_START =          "#"
JSON_FILE_EXTENSION =        "json"

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

FLASHOPTIONS_FILENAME =      "_FLASHOPTIONS.json"

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
    return jsonDict 


def openBSDVersion(hostdef):
    openBSDVersionForHost = None
    global gLatestOpenBsdStableVersion
    if gLatestOpenBsdStableVersion == None:
        if not os.path.isfile(OPENBSD_VERSION_FILENAME):
            error("Missing OpenBSD release version file '%s'" % OPENBSD_VERSION_FILENAME)

        pattern = re.compile("\d{2,3}")
        try:
            with open(OPENBSD_VERSION_FILENAME) as f:
                releaseText = f.read()
        except:
            error("Can't read OpenBSD version file '%s': %s" % (OPENBSD_VERSION_FILENAME, sys.exc_info()))

        if not len(releaseText) == 2 or pattern.fullmatch(releaseText) == None:
            error("OpenBSD version file '%s' must be in NN format" % OPENBSD_VERSION_FILENAME)
        gLatestOpenBsdStableVersion = releaseText
    
    # 'Stable' OS flavor uses last released version number
    # 'Current' OS flavor uses last released version number + 1
    flavor = hostdef[HOSTMAP_FIELD_OSFLAVOR]
    if flavor == OSFLAVOR_STABLE:
        openBSDVersionForHost = gLatestOpenBsdStableVersion
    elif flavor == OSFLAVOR_CURRENT:
        openBSDVersionForHost = str(int(gLatestOpenBsdStableVersion) + 1)
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


def printHostConfigurationForDefinition(hostdef):
    board = hostdef[HOSTMAP_FIELD_BOARD]
    print("\n========= HOST CONFIGURATION =========")
    print("|        Hostname:  %s" % hostdef[HOSTMAP_FIELD_HOSTNAME])
    print("|            Role:  %s" % hostdef[HOSTMAP_FIELD_ROLE])
    print("|        Hardware:  %s (%s)" % (board, bootloaderBoardNameForBoard(board)))
    print("|  OpenBSD Flavor:  %s (%s / %s)" % (hostdef[HOSTMAP_FIELD_OSFLAVOR], sysArchNameForBoard(board), pkgArchNameForBoard(board)))
    print("|      IP Address:  %s" % hostdef[HOSTMAP_FIELD_ADMIN_IP])
    print("|     MAC Address:  %s" % hostdef[HOSTMAP_FIELD_MACADDR])
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
    configDirPath = None

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
    
    return configDirPath


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


def OortInit(argParser: OortArgs):
    assert not platform.system() == 'Windows', "OORT is unsafe to run on Windows"

    assertNotRootUser()

    # Identify what OS we are running on and initialize the OS-specific layer
    machdepInit()
    
    # Find the oort-config directory
    configDirPath = locateConfigDirectory()
    assert os.path.isdir(configDirPath), "A valid oort-config directory could not be found. You must specify its absolute path via the -c/--config-dir argument, the " + CONFIG_DIR_ENV_VAR_NAME + " environment variable, or the ~/" + CONFIG_DIR_ALIAS_FILENAME + " file, or by storing your configuration in the ~/" + CONFIG_DIR_DOT_DIRNAME + " directory."

    # Change current directory to oort-config directory
    os.chdir(configDirPath)

    # Get user-configurable settings
    readConfigFile()

    # Load host definitions
    print("Loading host definitions...")
    global gHostMap
    gHostMap = loadCSV(HOSTMAP_FILENAME)
    validateHostmap()
    
    return argParser.getArgs()
