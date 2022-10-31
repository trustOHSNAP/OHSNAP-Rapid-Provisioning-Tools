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
# masterDisks.py #
##################

PROGRAM_DESCRIPTION = 'Generate installation boot disk and set packages disk for one or more hosts'


# INTERNAL LIBRARIES
from OortArgs import OortArgs # must come first
from OortCommon import *
import OortCommon
from createSiteFiles import generateSitePackage, autoinstallConfigurationRootPathForHost


# STANDARD LIBRARIES
import base64
from pathlib import Path
import requests
from requests.compat import urljoin
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


# EXTERNAL LIBRARIES
import pycurl


#
# CONSTANTS
#
DOWNLOAD_ROOT_NAME =        "mirror"
STAGING_ROOT_NAME =         "staging"
NETBOOT_ROOT_NAME =         "netroot"
NETBOOT_RUNTIME_NAME =      "netboot"

STAGING_INSTALLDISK_NAME =  "install_boot_disk"
STAGING_SETSDISK_NAME =     "sets_packages_disk"

MIRROR_ROOT_HTTP_URL=       'https://cdn.openbsd.org/pub/OpenBSD/'

HASH_FILENAME =             "SHA256"
HASH_SIGNED_FILENAME =      "SHA256.sig"
INSTALL_IMAGE_BASENAME =    'miniroot'
INSTALL_IMAGE_EXTENSION =   '.img'

USES_PYCURL = True

SET_PACKAGE_DIR_LISTING_FILENAME = "index.txt"

SET_PACKAGE_NAMES = [
    "bsd",
    "bsd.mp",
    "bsd.rd",
    "base%VERSION.tgz",
    "comp%VERSION.tgz",
    "game%VERSION.tgz",
    "man%VERSION.tgz",
    "xbase%VERSION.tgz",
    "xfont%VERSION.tgz",
    "xserv%VERSION.tgz",
    "xshare%VERSION.tgz"
]

# some architectures may not have these
SET_PACKAGE_OPTIONAL_NAMES = [
    "bsd.mp"
]

# HTTP response codes
HTTP_OK = 200
HTTP_PARTIAL_CONTENT = 206
HTTP_CONTINUABLE_RESPONSE_CODES = [
    HTTP_OK,
    HTTP_PARTIAL_CONTENT
]

#
# GLOBAL VARIABLES
#
# Persistent
gVerifiedDownloads = set()
gBootloaderPackageInfoCache = dict()
# Per-host... must be reset!
gMissingOptionalPackageNames = dict()


#
# METHODS
#
def prepareDownloadDirectories(hostdef, buildRootPath):
    print("Preparing download directory tree in '%s'..." % buildRootPath)
    
    dlRootDirPath = os.path.join(buildRootPath, DOWNLOAD_ROOT_NAME)
    debug("Creating top-level download directory '%s'..." % dlRootDirPath)
    makeDirIfNeeded(dlRootDirPath)

    flavor = hostdef[HOSTMAP_FIELD_OSFLAVOR]
    if flavor == OSFLAVOR_STABLE:
        flavorDirName = openBSDVersion(hostdef)
    elif flavor == OSFLAVOR_CURRENT:
        flavorDirName = OPENBSD_CURRENT_DIRNAME
    else:
        error("Unknown OpenBSD flavor '%s'" % flavor)
        
    flavorDirPath = os.path.join(dlRootDirPath, flavorDirName)
    debug("Creating flavor download directory '%s'..." % flavorDirPath)
    makeDirIfNeeded(flavorDirPath)

    sysArch = sysArchNameForBoard(hostdef[HOSTMAP_FIELD_BOARD])
    pkgArch = pkgArchNameForBoard(hostdef[HOSTMAP_FIELD_BOARD])
    
    sysDirPath = os.path.join(flavorDirPath, sysArch)
    debug("Creating sysarch download directory '%s'..." % sysDirPath)
    makeDirIfNeeded(sysDirPath)

    pkgDirPath = os.path.join(flavorDirPath, OPENBSD_PACKAGES_DIRNAME, pkgArch)
    debug("Creating pkg download directory '%s'..." % pkgDirPath)
    makeDirIfNeeded(pkgDirPath)

    return {
        'system': sysDirPath,
        'package': pkgDirPath
    }


def prepareStagingDirectories(hostdef, buildRootPath):
    print("Preparing staging directory tree in '%s'..." % buildRootPath)
    
    stageRootDirPath = os.path.join(buildRootPath, STAGING_ROOT_NAME)
    debug("Creating top-level staging directory '%s'..." % stageRootDirPath)
    makeDirIfNeeded(stageRootDirPath)
    
    stageDirPath = os.path.join(stageRootDirPath, hostdef[HOSTMAP_FIELD_HOSTNAME])
    debug("Creating host staging directory '%s'..." % stageDirPath)
    makeDirIfNeeded(stageDirPath)
    
    installDirPath = os.path.join(stageDirPath, STAGING_INSTALLDISK_NAME)
    debug("Creating install-boot disk staging directory '%s'..." % installDirPath)
    makeDirIfNeeded(installDirPath)
    
    setsDirPath = os.path.join(stageDirPath, STAGING_SETSDISK_NAME)
    debug("Creating sets/packages disk staging directory '%s'..." % setsDirPath)
    makeDirIfNeeded(setsDirPath)
    
    return {
        'install': installDirPath,
        'sets': setsDirPath
    }


def prepareNetbootDirectories(hostdef, buildRootPath):
    print("Preparing netboot directory tree in '%s'..." % buildRootPath)
    
    netbootRuntimeDirPath = os.path.join(buildRootPath, NETBOOT_RUNTIME_NAME)
    debug("Creating netboot runtime directory '%s'..." % netbootRuntimeDirPath)
    makeDirIfNeeded(netbootRuntimeDirPath)
    
    netbootFsrootDirPath = os.path.join(netbootRuntimeDirPath, NETBOOT_ROOT_NAME)
    debug("Creating netboot fileroot directory '%s'..." % netbootFsrootDirPath)
    makeDirIfNeeded(netbootFsrootDirPath)
    
    netbootHostDirPath = os.path.join(netbootFsrootDirPath, hostdef[HOSTMAP_FIELD_HOSTNAME])
    debug("Creating netboot host-specific directory '%s'..." % netbootHostDirPath)
    makeDirIfNeeded(netbootHostDirPath)
    
    return {
        'netboot_runtime': netbootRuntimeDirPath,
        'netboot_root': netbootFsrootDirPath,
        'netboot_host': netbootHostDirPath,
    }


def lookupFilenameInSHA256DirectoryTable(hashFilePath, targetFilename):
    patternMatch = matchFilenamePatternInSHA256DirectoryTable(hashFilePath, targetFilename)
    return patternMatch['hash']

    
def matchFilenamePatternInSHA256DirectoryTable(hashFilePath, targetFilenamePattern):
    debug("matching pattern %s in %s" % (targetFilenamePattern, hashFilePath))
    result = dict()  # keys: 'filename', 'hash'
    sha256 = None
    with open(hashFilePath, "r") as hashFile:
        for line in hashFile:
            line = line.strip()
            # first check for hashes written in hexadecimal format
            debug("checking line %s" % line)
            lineSearch = re.search(r'^SHA256 \(([+\w._-]+)\) = ([0-9A-Fa-f]{64})$', line, re.IGNORECASE)
            if lineSearch:
                lineFilename = lineSearch.group(1)
                filenameScan = re.search('(' + targetFilenamePattern + ')', lineFilename)
                if filenameScan:
                    matchedFilename = filenameScan.group(1)
                    sha256 = lineSearch.group(2)
                    break
            else:
                # if not found, check again in Base64 format
                lineSearch = re.search(r'^SHA256 \(([+\w._-]+)\) = ([/\w=+]{44})$', line, re.IGNORECASE)
                if lineSearch:
                    lineFilename = lineSearch.group(1)
                    filenameScan = re.search('(' + targetFilenamePattern + ')', lineFilename)
                    if filenameScan:
                        matchedFilename = filenameScan.group(1)
                        sha256 = base64.b64decode(lineSearch.group(2)).hex()
                        break
    debug("lookup %s: %s = %s" % (hashFilePath, matchedFilename, sha256))
    result['hash'] = sha256
    result['filename'] = matchedFilename
    return result


def urlForHostInstallSets(hostdef):
    # Determine release number and URL for system install sets
    flavor = hostdef[HOSTMAP_FIELD_OSFLAVOR]
    if flavor == OSFLAVOR_STABLE:
        setsRemoteDirName = dottedVersion(openBSDVersion(hostdef))
    elif flavor == OSFLAVOR_CURRENT:
        setsRemoteDirName = OPENBSD_CURRENT_DIRNAME
    else:
        error("Unknown OpenBSD flavor '%s'" % flavor)

    setsUrl = urljoin(MIRROR_ROOT_HTTP_URL, setsRemoteDirName + '/')
    debug("setsUrl = %s" % setsUrl)
    return setsUrl


def bootloaderPackagesInfoForHost(hostdef):
    # key: package name/label
    # value: dictionary ->
    #           keys:   'pattern': package filename pattern
    #                   'archOverride': look for package in this architecture instead of native arch    
    bootloaderPackagesInfo = dict()

    hostname = hostdef[HOSTMAP_FIELD_HOSTNAME]
    
    global gBootloaderPackageInfoCache

    if hostname in gBootloaderPackageInfoCache:
        debug("bootloaderPackagesInfoForHost(): found '%s' = %r" % (hostname, gBootloaderPackageInfoCache[hostname]))
        bootloaderPackagesInfo = gBootloaderPackageInfoCache[hostname]
    else:
        debug("bootloaderPackagesInfoForHost(): creating '%s'" % hostname)
        setsUrl = urlForHostInstallSets(hostdef)
    
        boardName = hostdef[HOSTMAP_FIELD_BOARD]
        pkgArchName = pkgArchNameForBoard(boardName)

        # arm64, arm32, and riscv64 all use u-boot
        # from arm64's packages repo, for some reason.
        if pkgArchName == "aarch64" or pkgArchName == "arm" or pkgArchName == "riscv64":
            archSetsUrl = urljoin(setsUrl, 'aarch64' + '/')
            ubootPackageUrlPattern = r'u-boot-' + pkgArchName + r'-[-\w.]+\.tgz'
            bootloaderPackagesInfo['u-boot'] = {
                'pattern': ubootPackageUrlPattern,
                'archOverride': 'aarch64',
                'tarContentsBoardParentPath': 'share/u-boot/',
            }

        # In general, each board may specify different bootloader files
        if  boardName == "rockpi4" or \
            boardName == "rock64" or \
            boardName == "rockpro64" or \
            boardName == "pinebookpro":
            bootloaderPackagesInfo['u-boot']['tarContentsExtractBoardChildPaths'] = [
                'idbloader.img',
                'u-boot.itb'
            ]
        elif boardName == "beagleboneblack":
            bootloaderPackagesInfo['u-boot']['tarContentsExtractBoardChildPaths'] = [
                'MLO',
                'u-boot.img'
            ]

        gBootloaderPackageInfoCache[hostname] = bootloaderPackagesInfo
        
    return bootloaderPackagesInfo


def downloadUrl(url, destPath):
    debug("[download] %s -> %s" % (url, destPath))
    
    with open(destPath, "wb") as destFile:
        with urllib.request.urlopen(url) as response:
            shutil.copyfileobj(response, destFile)

    # XXX NEED TO ABORT FOR FAILED DOWNLOADS
    

def callbackDownloadProgress(finalSize, currentSize, ignore1, ignore2):
    try:
        percent = float(currentSize)/float(finalSize)
    except:
        percent = 0
    sys.stdout.write("\r%s %3i%%" % ("Download Progress: ", percent*100))
    
    
def isDownloadRequired(filename, kind):
    required = True
    if kind == "sets_package":
        if filename in SET_PACKAGE_OPTIONAL_NAMES:
            required = False
    return required


# 'kind' is an underscore-separated parameter combining the file's intended "usage"
# (i.e., one of the keys returned in prepareStagingDirectories()) and its "source"
# location (i.e., one of the keys returned in prepareDownloadDirectories()), e.g.,
# "install_system", "install_package", "sets_package"
def downloadResumableUrl(url, destPath, kind):
    debug("[rdownload][%s] %s -> %s" % (kind, url, destPath))

    downloadSucceeded = False
    
    if USES_PYCURL:
        c = pycurl.Curl()
        c.setopt(pycurl.URL, url)
        c.setopt(pycurl.FOLLOWLOCATION, 1)
        c.setopt(pycurl.MAXREDIRS, 5)
        c.setopt(pycurl.NOPROGRESS, False)
        c.setopt(pycurl.XFERINFOFUNCTION, callbackDownloadProgress)
        c.setopt(pycurl.FAILONERROR, 1)

        if os.path.exists(destPath):
            f = open(destPath, "ab")
            c.setopt(pycurl.RESUME_FROM, os.path.getsize(destPath))
        else:
            f = open(destPath, "wb")
        c.setopt(pycurl.WRITEDATA, f)
    
        try:
            c.perform()
        except:
            if os.path.getsize(destPath) == 0:
                os.remove(destPath)
        print("") # need a newline after c.perform()'s repeated invocations of callbackDownloadProgress()
        
        response = c.getinfo(pycurl.RESPONSE_CODE)
        if not response in HTTP_CONTINUABLE_RESPONSE_CODES:
            print("Failed to download %s; got HTTP response code %i" % (url, response))
            downloadSucceeded = False
        else:
            downloadSucceeded = True
    else:
        error("No non-pycurl implementation yet!")
        downloadSucceeded = False

    if not downloadSucceeded:
        remoteFilename = os.path.basename(urllib.parse.urlsplit(url).path)
        if isDownloadRequired(remoteFilename, kind):
            error("Can't proceed without required %s download '%s'" % (kind, remoteFilename))
        else:
            global gMissingOptionalPackageNames
            if kind not in gMissingOptionalPackageNames:
                gMissingOptionalPackageNames[kind] = set()
            gMissingOptionalPackageNames[kind].add(remoteFilename)
            debug("Added %s to %s missing optional packages" % (remoteFilename, kind))
        
    return downloadSucceeded


def downloadResumableUrlIfNeeded(url, destPath, kind):
    debug("[rdownload?][%s] %s -> %s" % (kind, url, destPath))

    downloadSucceeded = False
    localHash = None
    remoteHash = None
    
    # maintain a global cache of everything downloaded since the program began
    if not destPath in gVerifiedDownloads:
        if os.path.isfile(destPath):
            # First compare local file size to remote file size
            remoteSize = int(requests.head(url).headers.get('content-length', 0))
            localSize = os.path.getsize(destPath)
            debug("localSize = %i, remoteSize = %i" % (localSize, remoteSize))
            # If local file is smaller, resume download
            if localSize < remoteSize:
                print("resuming download (%s -> %s) at %i of %i bytes" % (url, destPath, localSize, remoteSize))
                downloadSucceeded = downloadResumableUrl(url, destPath, kind)
            # If local file is larger, automatically do a full redownload
            elif localSize > remoteSize:
                print("local download (%s -> %s) too large (%s bytes; %s expected); redownloading" % (url, destPath, localSize, remoteSize))
                os.remove(destPath)
                downloadSucceeded = downloadResumableUrl(url, destPath, kind)
            else:
                # complete file already exists - nothing to do
                debug("%s already exists; %s bytes" % (destPath, localSize))
                downloadSucceeded = True
        else:
            downloadSucceeded = downloadResumableUrl(url, destPath, kind)

        if downloadSucceeded:
            # Compare SHA256 hashes in all cases in case server file changed
            sha256FilePath = os.path.join(os.path.dirname(destPath), HASH_FILENAME)
            if not os.path.isfile(sha256FilePath):
                error("no directory hash file found at %s" % sha256FilePath)
            remoteFilename = os.path.basename(urllib.parse.urlsplit(url).path)
            remoteHash = lookupFilenameInSHA256DirectoryTable(sha256FilePath, remoteFilename)
            assert remoteHash is not None, "Can't find '%s' in '%s'" % (remoteFilename, sha256FilePath)

            localHash = sha256(destPath)
            assert localHash is not None, "Can't compute hash for '%s'" % destPath
            debug("lhash/rhash: %s / %s" % (localHash, remoteHash))
    
            # If hash mismatch, try full download one more time
            if localHash != remoteHash:
                print("Hash mismatch! %s (%s) != %s (%s)" % (url, remoteHash, destPath, localHash))
                os.remove(destPath)
                localHash = None
                downloadSucceeded = downloadResumableUrl(url, destPath, kind)
                if downloadSucceeded:
                    localHash = sha256(destPath)
                    if localHash != remoteHash:
                        error("SHA256 hashes do not match after redownload! %s (%s) != %s (%s)" % (url, remoteHash, destPath, localHash))
        
            if downloadSucceeded and localHash is not None and remoteHash is not None and localHash == remoteHash:
                print("Hash verified: %s" % localHash)
                gVerifiedDownloads.add(destPath)
            else:
                downloadSucceeded = False
    else:
        debug("-> %s already downloaded; skipping" % destPath)
        downloadSucceeded = True

    return downloadSucceeded
        
    
def downloadImagesForHost(hostdef):
    boardName = hostdef[HOSTMAP_FIELD_BOARD]
    openBSDVersionString = openBSDVersion(hostdef)
    
    # Create download directories
    outputDirs = prepareDownloadDirectories(hostdef, configValue(CONFIG_KEY_BUILD_ROOT_PATH))
    debug("Download directories: %r" % outputDirs)
    
    # Determine URL for downloading install sets based on OpenBSD version and architecture
    setsUrl = urlForHostInstallSets(hostdef)
    archSetsUrl = urljoin(setsUrl, sysArchNameForBoard(boardName) + '/')
    debug("archSetsUrl = %s" % archSetsUrl)

    print("Downloading install sets from %s..." % archSetsUrl)
    
    # Always download the latest SHA256 file for the system install sets
    print("Getting system SHA256 hashes...")
    hashUrl = urljoin(archSetsUrl, HASH_FILENAME)
    downloadUrl(hashUrl, os.path.join(outputDirs['system'], HASH_FILENAME))
    hashSigUrl = urljoin(archSetsUrl, HASH_SIGNED_FILENAME)
    downloadUrl(hashSigUrl, os.path.join(outputDirs['system'], HASH_SIGNED_FILENAME))

    # Download install image
    installImageName = INSTALL_IMAGE_BASENAME + installImageNameInfixForBoard(boardName) + openBSDVersionString + INSTALL_IMAGE_EXTENSION
    print("Downloading '%s'..." % installImageName)
    installImageUrl = urljoin(archSetsUrl, installImageName)
    downloadResumableUrlIfNeeded(installImageUrl, os.path.join(outputDirs['system'], installImageName), 'install_system')

    # Download bootloader package(s), if any
    bootloaderPackagesInfo = bootloaderPackagesInfoForHost(hostdef)
    if len(bootloaderPackagesInfo):
        pkgBaseUrl = urljoin(setsUrl, OPENBSD_PACKAGES_DIRNAME + '/')
        
        # Download bootloader package(s)
        for pkgLabel, pkgInfo in bootloaderPackagesInfo.copy().items():
            pkgUrlPattern = pkgInfo['pattern']
            pkgArch = pkgInfo.get('archOverride', pkgArchNameForBoard(boardName)) # Check if we need to override the architecture of the package
            archPkgsUrl = urljoin(pkgBaseUrl, pkgArch + '/')
            debug("archPkgsUrl = %s" % archPkgsUrl)

            # Download the latest SHA256 file for packages
            print("Getting package SHA256 hashes...")
            hashUrl = urljoin(archPkgsUrl, HASH_FILENAME)
            hashDownloadPath = os.path.join(outputDirs['package'], HASH_FILENAME)
            downloadUrl(hashUrl, hashDownloadPath)
            hashSigUrl = urljoin(archPkgsUrl, HASH_SIGNED_FILENAME)
            hashSigDownloadPath = os.path.join(outputDirs['package'], HASH_SIGNED_FILENAME)
            downloadUrl(hashSigUrl, hashSigDownloadPath)

            # Find exact filename by matching pattern to hash file entries
            hashMatchResult = matchFilenamePatternInSHA256DirectoryTable(hashDownloadPath, pkgUrlPattern)
            assert 'filename' in hashMatchResult, "Failed to match bootloader package file pattern '%s'" % pkgUrlPattern
            pkgFilename = hashMatchResult['filename']
            print("Downloading '%s'..." % pkgFilename)
            pkgUrl = urljoin(archPkgsUrl, pkgFilename)
            downloadResumableUrlIfNeeded(pkgUrl, os.path.join(outputDirs['package'], pkgFilename), 'install_package')
            
            # Insert the exact filename back into the original info dict
            global gBootloaderPackageInfoCache
            debug("before: %r" % gBootloaderPackageInfoCache)
            gBootloaderPackageInfoCache[hostdef[HOSTMAP_FIELD_HOSTNAME]][pkgLabel]['filename'] = pkgFilename
            debug("after: %r" % gBootloaderPackageInfoCache)

    outputDirs['installImageName'] = installImageName
    
    # Download fileset packages
    print("Getting fileset packages...")
    setPackageFilenames = list()
    for setPackagePattern in SET_PACKAGE_NAMES:
        setPackageFilename = setPackagePattern.replace('%VERSION', openBSDVersionString)
        setPackageFilenames.append(setPackageFilename)
        print("Downloading '%s'..." % setPackageFilename)
        setPackageUrl = urljoin(archSetsUrl, setPackageFilename)
        downloadResumableUrlIfNeeded(setPackageUrl, os.path.join(outputDirs['system'], setPackageFilename), 'sets_package')
    
    outputDirs['setPackageFilenames'] = setPackageFilenames

    return outputDirs


def extractFilesFromTarIntoFlatDirectory(tarPath, memberPaths, destDir):
    with tempfile.TemporaryDirectory() as tmpDirName:
        tmpDirPath = Path(tmpDirName)
        with tarfile.open(tarPath, "r:*") as tar:
            for memberPath in memberPaths:
                extractedPath = os.path.join(destDir, os.path.basename(memberPath))
                tmpFilePath = os.path.join(tmpDirPath, memberPath) # The file is extracted as full path, not a top-level file, so extract in a temporary directory and then move the file up manually
                debug("Extract tar path %s -> %s -> %s" % (memberPath, tmpFilePath, extractedPath))
                tar.extract(memberPath, path=tmpDirPath, set_attrs=False)
                shutil.move(tmpFilePath, extractedPath)

    
def manifestFileInfo(filename, path, boardnameForImageFlashing = None):
    abspath = os.path.abspath(path)
    assert not containsWhitespace(filename)
    assert not containsWhitespace(abspath)
    assert os.path.isabs(abspath)
    imageInfo = {
        'filename': filename,
        'abspath': abspath
    }

    if boardnameForImageFlashing is not None:
        flashOptionsForAllImages = installImageFlashOptionsForBoard(boardnameForImageFlashing)
        debug("Board '%s' flash options: %r" % (boardnameForImageFlashing, flashOptionsForAllImages))
        if flashOptionsForAllImages is not None:
            if filename in flashOptionsForAllImages:
                imageInfo['ddOptions'] = flashOptionsForAllImages[filename]['ddOptions']

    return imageInfo


def stageImagesForHost(hostdef, downloadDirPaths):
    print("Staging install & set disks...")

    installerDiskManifest = list()
    setsDiskManifest = list()
    
    hostName = hostdef[HOSTMAP_FIELD_HOSTNAME]
    boardName = hostdef[HOSTMAP_FIELD_BOARD]
    
    # Create staging directories
    outputDirs = prepareStagingDirectories(hostdef, configValue(CONFIG_KEY_BUILD_ROOT_PATH))
    debug("Staging directories: %r" % outputDirs)

    #
    # BOOT/INSTALLER DISK
    #
    
    # Copy install image
    print("Copying install image (if needed)...")
    imageName = downloadDirPaths['installImageName']
    installImageSrcPath = os.path.join(downloadDirPaths['system'], imageName)
    installImageDstPath = os.path.join(outputDirs['install'], imageName)
    copyFileIfNeeded(installImageSrcPath, installImageDstPath)
    installerDiskManifest.append(manifestFileInfo(imageName, installImageDstPath, boardName))

    # Extract bootloader package(s), if any
    bootloaderPackagesInfo = bootloaderPackagesInfoForHost(hostdef)
    for pkgName, pkgInfo in bootloaderPackagesInfo.items():
        print("Staging '%s'..." % pkgName)
        debug("pkgInfo = %r" % pkgInfo)
        pkgPath = os.path.join(downloadDirPaths['package'], pkgInfo['filename'])
        debug("stage file path = %s" % pkgPath)
        tarBoardParentPath = pkgInfo['tarContentsBoardParentPath']
        tarBoardName = bootloaderBoardNameForBoard(boardName)
        tarBoardChildPaths = pkgInfo['tarContentsExtractBoardChildPaths']
        tarMemberPaths = list()
        for childPath in tarBoardChildPaths:
            tarMemberPath = os.path.join(os.path.join(tarBoardParentPath, tarBoardName), childPath)
            tarMemberPaths.append(tarMemberPath)
            imageName = os.path.basename(tarMemberPath)
            installerDiskManifest.append(manifestFileInfo(imageName, os.path.join(outputDirs['install'], imageName), boardName))
        extractFilesFromTarIntoFlatDirectory(pkgPath, tarMemberPaths, outputDirs['install'])

    #
    # FILESETS DISK
    #
    print("Copying sets...")
    hashFileNames = [ HASH_FILENAME, HASH_SIGNED_FILENAME ]
    for setPackageFilename in downloadDirPaths['setPackageFilenames'] + hashFileNames:
        global gMissingOptionalPackageNames
        if 'sets_package' in gMissingOptionalPackageNames and setPackageFilename in gMissingOptionalPackageNames['sets_package']:
            debug("Skipping missing optional 'sets_package' file '%s'" % setPackageFilename)
            continue
        print("Staging '%s'..." % setPackageFilename)
        setPackageFileSrcPath = os.path.join(downloadDirPaths['system'], setPackageFilename)
        setPackageFileDstPath = os.path.join(outputDirs['sets'], setPackageFilename)
        copyFileIfNeeded(setPackageFileSrcPath, setPackageFileDstPath)
        setsDiskManifest.append(manifestFileInfo(setPackageFilename, setPackageFileDstPath))
    
    # Generate and copy the site.tgz file
    sitePackagePath = generateSitePackage(hostName)
    sitePackageName = os.path.basename(sitePackagePath)
    print("Staging '%s'..." % sitePackageName)
    setPackageFileDstPath = os.path.join(outputDirs['sets'], sitePackageName)
    copyFileIfNeeded(sitePackagePath, setPackageFileDstPath)
    setsDiskManifest.append(manifestFileInfo(sitePackageName, setPackageFileDstPath))
    
    # Generate index.txt by running 'ls -l' so that it includes our site.tgz file to be picked up by autoinstall    
    print("Generating set package directory listing...")
    setPackageDirPath = outputDirs['sets']
    cmdResult = subprocess.run(["ls", "-l", os.path.abspath(setPackageDirPath)], capture_output = True, encoding="utf-8", check = True)
    setPackageDirListing = cmdResult.stdout
    setPackageDirListingPath = os.path.join(setPackageDirPath, SET_PACKAGE_DIR_LISTING_FILENAME)
    with open(setPackageDirListingPath, 'w') as dirListingFile:
        dirListingFile.write(setPackageDirListing)
    setsDiskManifest.append(manifestFileInfo(SET_PACKAGE_DIR_LISTING_FILENAME, setPackageDirListingPath))
    
    # Add any (available) files needed for autoinstall
    print("Adding autoinstall files...")
    for root, dirs, files in os.walk(autoinstallConfigurationRootPathForHost(hostdef)):
        for file in files:
            src = os.path.join(root, file)
            filename = os.path.basename(src)
            dst = os.path.join(outputDirs['sets'], filename)
            copyFileIfNeeded(src, dst)
            setsDiskManifest.append(manifestFileInfo(filename, dst))

    return {
        'installer_disk': installerDiskManifest,
        'sets_disk': setsDiskManifest
    }
    

def generateMasteringImageForHostname(hostname):
    # Clear any globals that may have gotten reused
    global gMissingOptionalPackageNames
    gMissingOptionalPackageNames = dict()

    print("Begin mastering image for host '%s'..." % hostname)
    # Load host definition
    hostdef = getHostDefinition(hostname)
    if hostdef is None:
        error("No host found with name '%s'" % hostname)
    printHostConfigurationForDefinition(hostdef)

    downloadDirs = downloadImagesForHost(hostdef)
    
    diskManifests = stageImagesForHost(hostdef, downloadDirs)

    print("Finished mastering image for host '%s'." % hostname)
    
    debug("diskManifests = %r" % diskManifests)
    
    return diskManifests


def main(argv):
    global PROGRAM_DESCRIPTION
    argParser = OortArgs(PROGRAM_DESCRIPTION)
    argParser.addArg("hostnames", nargs='*', help="Name(s) of host(s) for which to generate mastering images")
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
        generateMasteringImageForHostname(hostname)
        completedCount += 1
    
    print("%i mastering image%s generated." % (completedCount, "" if completedCount == 1 else "s"))
	

if __name__ == "__main__":
    main(sys.argv[1:])
