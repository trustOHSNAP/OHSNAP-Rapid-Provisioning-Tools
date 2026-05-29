#!/usr/bin/env python3
# For Python 3.9.10 or later

# ISC License
# 
# Copyright (c) 2022-2026 OHSNAP
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
# createSiteFiles.py #
######################

PROGRAM_DESCRIPTION = 'Generate site.tgz custom package sets on a per-host basis'


# INTERNAL LIBRARIES
from OortArgs import OortArgs # must come first
import OortCommon
from OortCommon import *


# STANDARD LIBRARIES
import errno
import shutil
import sys
import tempfile
import tarfile


#
# CONSTANTS
#
BUILD_DIR =                  "site"
BUILD_DIR_DESTROOT_NAME =    "siteroot"
AUTOINSTALL_DIR =            "autoinstall"

MANIFEST_FILENAME =          "_MANIFEST.csv"
MANIFEST_FIELD_USER =        "USER"
MANIFEST_FIELD_GROUP =       "GROUP"
MANIFEST_FIELD_PERMISSIONS = "PERM"
MANIFEST_FIELD_PATH =        "ABSPATH"

MANIFEST_SUBSTITUTION_DOTFILE = "_DOT."
MANIFEST_SUBSTITUTION_AUTOGEN = "_AUTOGEN_"

PACKAGES_FILENAME =          "_PACKAGES.csv"
PACKAGES_FIELD_NAME =        "PACKAGE"

SITE_PACKAGE_NAME_TEMPLATE = "site%s-%s.tgz"  # first arg = release, second arg = host
INSTALL_SCRIPT_ABSPATH =     "/install.site"
FIRSTBOOT_APPEND_ABSPATH =   "/etc/rc.firsttime"
ETCHOSTS_ABSPATH =           "/etc/hosts"
ETCHOSTS_APPEND_ABSPATH =    "/root/post_install_hosts_append"
ETCINSTALLURL_ABSPATH =      "/etc/installurl"
ETCINSTALLURL_DEFAULT_URL =  "https://cdn.openbsd.org/pub/OpenBSD"
AUTOINSTALL_FILENAME =       "install.conf"
AUTODISKLABEL_FILENAME_PTN = "(disklabel.[\w]+[0-9]+)"

AUTOGEN_FILENAME_PACKAGES =             "_AUTOGEN_post_install_package_list.txt"
AUTOGEN_FILENAME_SITE_INSTALL_APPEND =  "_AUTOGEN_install.site"
AUTOGEN_FILENAME_AUTOINSTALL =          "_AUTOGEN_" + AUTOINSTALL_FILENAME
AUTOGEN_FILEPATTERN_AUTODISKLABEL =     "_AUTOGEN_" + AUTODISKLABEL_FILENAME_PTN

AUTOINSTALL_VAR_HOSTNAME =        "__OORT_TEMPLATE_HOSTNAME__"
AUTOINSTALL_VAR_NETBOOT_HOST_IP = "__OORT_TEMPLATE_NETBOOT_HOST_IP__"
AUTOINSTALL_VAR_OPENBSD_VERSION = "__OORT_TEMPLATE_OPENBSD_SHORTVERSION__"

TMP_DIR_PREFIX = "network.ohsnap.oort.sitegen_"


#
# GLOBAL VARIABLES
#
# Per-host... must be reset!
gPermissionsMapping = dict()
gInstallSiteScriptAppend = ''


#
# METHODS
#    
def prepareOutputDirectories(hostname):
    buildRootPath = configValue(CONFIG_KEY_BUILD_ROOT_PATH)

    finalOutputDirectoryPath = os.path.join(buildRootPath, BUILD_DIR, hostname, BUILD_DIR_DESTROOT_NAME)
    makeDirIfNeeded(finalOutputDirectoryPath)
    
    intermediateBuildDirectoryPath = tempfile.mkdtemp(prefix=TMP_DIR_PREFIX)

    autoinstallOutputDirectoryPath = os.path.join(buildRootPath, BUILD_DIR, hostname, AUTOINSTALL_DIR)
    makeDirIfNeeded(autoinstallOutputDirectoryPath)

    return { 'final': finalOutputDirectoryPath, 'intermediate': intermediateBuildDirectoryPath, 'autoinstall': autoinstallOutputDirectoryPath }
    

def manifestPathForDomain(domain, hostdef):
    return rootRelativePathForDomainResource(domain, hostdef, MANIFEST_FILENAME)


def packagesPathForDomain(domain, hostdef):
    return rootRelativePathForDomainResource(domain, hostdef, PACKAGES_FILENAME)


def autoinstallConfigurationRootPathForHost(hostdef):
    return os.path.join(configValue(CONFIG_KEY_BUILD_ROOT_PATH), BUILD_DIR, hostdef[HOSTMAP_FIELD_HOSTNAME], AUTOINSTALL_DIR)


def checkTemplateDirectoryStructure(hostdef):
    print("Verifying template directory structure...")
    debug("Current directory: %s" % os.getcwd())
        
    for domain in DOMAINS:
        if not os.path.isdir(domain):
            error("Configuration directory is missing domain directory '%s'" % domain)
        manifestPath = manifestPathForDomain(domain, hostdef)
        if not os.path.isfile(manifestPath):
            error("Configuration directory is missing %s manifest '%s'" % (domain, manifestPath))


def performSubstitutionsOnPath(path):
    path = path.replace(MANIFEST_SUBSTITUTION_DOTFILE, ".")
    path = path.replace(MANIFEST_SUBSTITUTION_AUTOGEN, "")
    return path
    

def isAutogenFile(sourcePath):
    return False if sourcePath.find(MANIFEST_SUBSTITUTION_AUTOGEN) == -1 else True


def processAutogenFile(sourcePath, destPath, domain, hostdef):
    sourceName = os.path.basename(sourcePath)
    
    # /root/post_install_package_list.txt
    if sourceName == AUTOGEN_FILENAME_PACKAGES:
        packagesSourceDict = loadCSV(packagesPathForDomain(domain, hostdef))
        packagesDestList = list()
        for packageEntry in packagesSourceDict:
            packagesDestList.append(packageEntry[PACKAGES_FIELD_NAME])

        debug("Autogen: Write to '%s': %r" % (destPath, packagesDestList))
        with open(destPath, 'a') as packagesTextFile:
            for package in packagesDestList:
                packagesTextFile.write(str(package) + '\n')
                
    
    # /install.site
    elif sourceName == AUTOGEN_FILENAME_SITE_INSTALL_APPEND:
        global gInstallSiteScriptAppend
        installSiteScriptAppendFilePath = rootRelativePathForDomainResource(domain, hostdef, INSTALL_SCRIPT_ABSPATH)
        debug("Checking for '%s'..." % installSiteScriptAppendFilePath)
        if os.path.isfile(installSiteScriptAppendFilePath):
            with open(installSiteScriptAppendFilePath, 'r') as installSiteScriptAppendFile:
                print("installSiteScriptAppendFile = %s" % installSiteScriptAppendFile)
                gInstallSiteScriptAppend += installSiteScriptAppendFile.read()


    # autoinstall / install.conf file for autoinstallation
    elif sourceName == AUTOGEN_FILENAME_AUTOINSTALL:
        # The autoinstall file doesn't actually go into the site package, so we need to manually move it up into the host output parent directory
        destPath = os.path.join(autoinstallConfigurationRootPathForHost(hostdef), AUTOINSTALL_FILENAME)
        # Copy to the destination, performing template variable substitution along the way
        varSubs = { AUTOINSTALL_VAR_HOSTNAME:        hostdef[HOSTMAP_FIELD_HOSTNAME],
                    AUTOINSTALL_VAR_NETBOOT_HOST_IP: configValue(CONFIG_KEY_NETBOOT_HOST_IP),
                    AUTOINSTALL_VAR_OPENBSD_VERSION: openBSDVersion(hostdef) }
        with open(sourcePath, 'r') as srcAutoinstallConf:
            with open(destPath, 'w') as dstAutoinstallConf:
                dstAutoinstallConf.write(replaceVariablesInString(srcAutoinstallConf.read(), varSubs))
        

    # autodisklabel file(s) for autoinstallation
    elif autodisklabelNameMatch := re.match(AUTOGEN_FILEPATTERN_AUTODISKLABEL, sourceName):
        # The autodisklabel file(s) don't actually go into the site package, so we need to manually move them up into the host output parent directory
        autodisklabelName = autodisklabelNameMatch.group(1)
        destPath = os.path.join(autoinstallConfigurationRootPathForHost(hostdef), autodisklabelName)
        shutil.copyfile(sourcePath, destPath)

#     else:
#         error("'%s' is not an autogenerated file" % sourcePath)


def setArchivedFilePermissions(tarinfo):
    absPath = '/' + tarinfo.name        # the permission lookup key should be relative to absolute root since this script works in abs paths...
    tarinfo.name = './' + tarinfo.name  # ...but for OpenBSD, which chroot()s during install, path needs to be relative

    tarinfo.uname = gPermissionsMapping[absPath]['user']
    tarinfo.gname = gPermissionsMapping[absPath]['group']
    tarinfo.mode = gPermissionsMapping[absPath]['perm']
    debug("[tarinfo] name = %s, user = %s, group = %s, mode = %i" % (tarinfo.name, tarinfo.uname, tarinfo.gname, tarinfo.mode))
    return tarinfo
    
    
def makeTarFile(sourceDir, destPath):
    with tarfile.open(destPath, "w:gz") as tar:
        tar.add(sourceDir, arcname='/', filter=setArchivedFilePermissions)


def generateHostConfigurationForDomain(domain, hostdef, outputBaseDir):
    manifestPath = manifestPathForDomain(domain, hostdef)
    manifest = loadCSV(manifestPath)
    duplicatePathPrevention = set()
    for override in manifest:
        absPath = override[MANIFEST_FIELD_PATH]
        if absPath in duplicatePathPrevention:
            error("Manifest contains multiple entries for '%s'" % absPath)
        duplicatePathPrevention.add(absPath)
        print("%s\t%s\t%s\t%s" % (override[MANIFEST_FIELD_PERMISSIONS], override[MANIFEST_FIELD_USER], override[MANIFEST_FIELD_GROUP], absPath))
        if not absPath.startswith("/"):
            error("%s manifest contains a non-absolute path ('%s')" % (domain, absPath))
        relPath = absPath[1:]
        
        sourcePath = os.path.join(os.path.dirname(manifestPath), relPath)
        destPath = os.path.join(outputBaseDir, performSubstitutionsOnPath(relPath))
        
        # add entry to global file permissions mapping if it doesn't already exist (i.e. first-in precedence)
        global gPermissionsMapping
        transformedAbsPath = performSubstitutionsOnPath(absPath)
        if not transformedAbsPath in gPermissionsMapping:
            gPermissionsMapping[transformedAbsPath] = {
                'user': override[MANIFEST_FIELD_USER],
                'group': override[MANIFEST_FIELD_GROUP],
                'perm': int(override[MANIFEST_FIELD_PERMISSIONS], 8),
            }
        
        debug("\t\t\t\t\t%s  -->  %s" % (sourcePath, destPath))
        if isAutogenFile(sourcePath):
            processAutogenFile(sourcePath, destPath, domain, hostdef)
        else:
            if not os.path.exists(sourcePath):
                error("Manifest absolute path '%s' does not correspond to an existing file or folder at '%s'" % (absPath, sourcePath))
            if os.path.isdir(sourcePath):
                # dir may have already been created by previous domain - ok to skip
                if not os.path.isdir(destPath):
                    os.mkdir(destPath)
            elif os.path.isfile(sourcePath):
                shutil.copyfile(sourcePath, destPath)
            else:
                error("Source path '%' is neither a file nor folder" % sourcePath)
    

# Tasks:
# - append /etc/hosts
def generateHostInstallSiteFile(hostname, destRootPath):
    print("Generating host install.site file...")
    debug("destRootPath = %s" % destRootPath)
    #
    # /etc/hosts
    #
    
    # Generate hosts append file in /root/
    print("Generating '%s'..." % ETCHOSTS_APPEND_ABSPATH)
    hosts = dict()
    for hostdef in OortCommon.gHostMap:
        hosts[hostdef[HOSTMAP_FIELD_HOSTNAME]] = hostdef[HOSTMAP_FIELD_ADMIN_IP]
    destPath = os.path.join(destRootPath, ETCHOSTS_APPEND_ABSPATH[1:])
    debug("Write to '%s'" % (destPath))
    with open(destPath, 'w') as etcHostsAppendFile:
        for hostname, hostip in hosts.items():
            etcHostsAppendFile.write("%s\t%s\n" % (str(hostip), str(hostname)))
    
    # Create /install.site script
    print("Generating '%s'..." % INSTALL_SCRIPT_ABSPATH)
    varSubs = { "$ETCHOSTS_APPEND_ABSPATH": ETCHOSTS_APPEND_ABSPATH,
                "$ETCHOSTS_ABSPATH":        ETCHOSTS_ABSPATH,
                "$ETCINSTALLURL_ABSPATH":   ETCINSTALLURL_ABSPATH,
                "$ETCINSTALLURL":           hostOptionsValue(hostname, HOSTOPTIONS_KEY_INSTALLURL, ETCINSTALLURL_DEFAULT_URL)
              }
    installSiteScript = replaceVariablesInString(
'''#!/bin/sh

# add autogenerated hosts
if [ -f $ETCHOSTS_APPEND_ABSPATH ]
then
    cat $ETCHOSTS_APPEND_ABSPATH >> $ETCHOSTS_ABSPATH
fi

# restore /etc/installurl, which would have been overwritten during
# autoinstall to point to the temporary autoinstall server
echo "$ETCINSTALLURL" > $ETCINSTALLURL_ABSPATH

''', varSubs)
    global gInstallSiteScriptAppend
    installSiteScript += gInstallSiteScriptAppend
    destPath = os.path.join(destRootPath, INSTALL_SCRIPT_ABSPATH[1:])
    debug("Write to '%s'" % (destPath))
    with open(destPath, 'w') as installSiteScriptFile:
        installSiteScriptFile.write(installSiteScript)
    

def generateSitePackage(hostname):
    # clear any globals that may have gotten reused
    global gPermissionsMapping
    global gInstallSiteScriptAppend
    gPermissionsMapping = dict()
    gInstallSiteScriptAppend = ''

    print("Begin generating site package set for '%s'..." % hostname)
    # Load host definition
    hostdef = getHostDefinition(hostname)
    if hostdef is None:
        error("No host found with name '%s'" % hostname)

    # Check template directory structure
    checkTemplateDirectoryStructure(hostdef)

    # Create/verify build directories
    outputDirs = prepareOutputDirectories(hostname)
    debug("Output directories: %r" % outputDirs)
    
    # Print host configuration
    printHostConfigurationForDefinition(hostdef)
    
    for domain in DOMAINS:
        print("Generating '%s' overrides..." % domain)
        generateHostConfigurationForDomain(domain, hostdef, outputDirs['intermediate'])
        
    generateHostInstallSiteFile(hostname, outputDirs['intermediate'])

    # move intermediate build products into final location if we've made it to this point
    print("Moving merged root into %s..." % os.path.dirname(outputDirs['final']))

    src = outputDirs['intermediate']
    dst = os.path.dirname(outputDirs['final'])
    debug("move(%s, %s)" % (src, dst))
    shutil.move(src, dst)

    src = outputDirs['final']
    dst = outputDirs['intermediate']
    debug("move(%s, %s)" % (src, dst))
    shutil.move(src, dst)

    src = os.path.join(os.path.dirname(outputDirs['final']), os.path.basename(outputDirs['intermediate']))
    dst = outputDirs['final']
    debug("rename(%s, %s)" % (src, dst))
    os.rename(src, dst)
    
    # Determine OpenBSD release version and corresponding site package name
    sitePackageName = SITE_PACKAGE_NAME_TEMPLATE % (openBSDVersion(hostdef), hostname)
    debug("Site package name: %s" % sitePackageName)
    
    # create site.tgz
    print("Creating site package...")
    src = outputDirs['final']
    dst = os.path.join(os.path.dirname(outputDirs['final']), sitePackageName)
    debug("Writing archive of '%s' to '%s'" % (src, dst))
    makeTarFile(src, dst)
    
    print("Finished generating site package set for host '%s'.\n" % hostname)
    
    return os.path.abspath(dst)


def main(argv):
    global PROGRAM_DESCRIPTION
    argParser = OortArgs(PROGRAM_DESCRIPTION)
    argParser.addArg("hostnames", nargs='*', help="Name(s) of host(s) to be provisioned")
    args = OortInit(argParser)

    hostnames = args.hostnames

    completedCount = 0
    
    if hostnames == None or len(hostnames) == 0:
        hostnames = list()
        for hostdef in OortCommon.gHostMap:
            if not hostdef[HOSTMAP_FIELD_ROLE] == HOST_ROLE_VIRTUAL: # skip virtual entries
                hostnames.append(hostdef[HOSTMAP_FIELD_HOSTNAME])

    debug("Hosts enqueued: %r" % hostnames)
    
    for hostname in hostnames:
        generateSitePackage(hostname)
        completedCount += 1
    
    print("%i host%s generated." % (completedCount, "" if completedCount == 1 else "s"))
	
	
if __name__ == "__main__":
    main(sys.argv[1:])