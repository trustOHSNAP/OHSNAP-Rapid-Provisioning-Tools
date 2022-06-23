# OHSNAP OpenBSD Rapid Provisioning Tools ("OORT")

The **OHSNAP OpenBSD Rapid Provisioning Tools** (**OORT**) package is a set of software tools for fast, automated installation and provisioning of multiple devices with [OpenBSD](https://www.openbsd.org). It is useful for both speeding up develop & debug cycles and for final imaging of hardware deliverables or personal devices.

OORT is developed by the **[Open Hardware for Secure Networks and Privacy](https://github.com/trustOHSNAP)** (**OHSNAP**) project, but it is a standalone software package that runs independently of OHSNAP hardware. For more information on OHSNAP see the Wiki: [https://www.noisebridge.net/wiki/OHSNAP](https://www.noisebridge.net/wiki/OHSNAP)

***OORT is currently in early development and not yet ready for public use. This code is published only for internal use by the OHSNAP team. A public release will be made at a later date. USE AT YOUR OWN RISK!***


## License

OORT is released under an open source BSD license. The official source repository is available at https://github.com/trustOHSNAP/OHSNAP-Rapid-Provisioning-Tools

See the [LICENSE](https://github.com/trustOHSNAP/OHSNAP-Rapid-Provisioning-Tools/blob/main/LICENSE) file for full legal terms.


## Feature Overview

OORT provides tools to perform the following tasks:


- **`createSiteFiles.py`**: Generate per-host `site.tgz` [installer package files](https://man.openbsd.org/install.site.5) using a highly flexible, hierarchical templating scheme.
    - Package contents can be easily tailored to specific roles, hardware mainboards, individual hosts, and other parameters.
- **`masterDisks.py`**: Automatically download specific releases (or the latest snapshot) of all necessary OpenBSD boot disks, bootloaders, and installer package sets for all hosts, even across architectures. All files are checked against SHA256 hashes for integrity and to allow skipping already-downloaded files.
- **`flashInstall.py`**: Write an installer boot image onto a USB flash drive, SD card, or other media, taking into account hardware-specific requirements of various boards and architectures.
- **`autoinstall.py`**: Deploy a local netboot server (BOOTP + HTTP) to vend a complete end-to-end [autoinstallation](https://man.openbsd.org/autoinstall) to all targets connected to the same subnet, allowing for a complete or nearly complete hands-off provisioning of potentially many devices.


## Prerequisites

- Python 3.9.10 or newer
- [PycURL](https://pypi.org/project/pycurl/) 7.45 or newer
- A host system running a supported OS:
    - macOS (tested on Catalina)
    - OpenBSD (tested on 7.1)
- A supported release of OpenBSD you intend to install on your target(s) (does not need to be installed yet) - tested on 7.0-7.1


## Installation and Configuration

Before using any of the tools, you need to set up and configure OORT and tell it about your devices and your network.


### 1. Set up your host environment

A fully configured OORT environment is spread across three locations:

1. The directory containing the OORT software package. ("``oort-code``")
2. The directory containing your target device/network configuration. ("``oort-config``") (see Step 3)
3. The directory that will store all downloaded and generated files, including package sets, staging files, disk images, and netboot hierarchies ("``oort-build``")

Consider where you will want to store each of these directories. Here are some suggestions:

- Your ``oort-config`` is a valuable asset, likely containing sensitive administrator-level files and/or personal credentials that should not be world-readable. Keep it in a safe location. 
- Consider encapsulating your ``oort-config`` in a local ``git`` repository so that you can have change tracking and the ability to easily roll back from unsuccessful configurations. You should make a habit of committing a change every time you make one.
- The `oort-buid` directory will be large, possibly multiple gigabytes, depending on the number of targets in your network. Make sure that your storage device has plenty of room. If you use a data backup system, you may want to exclude this directory from automated backups since it only contains autogenerated data which you can easily recreate with `oort`.

### 2. Step 2

### 3. Step 3

## Usage

Each of the four tools can be used on its own. The `flashInstall` and `autoinstall` tools both first run `masterDisks` in order to deploy using the latest available OpenBSD packages. `autoinstall` also runs `createSiteFiles` in order to vend the latest site configuration to targets.

INSTRUCTIONS GO HERE


## Known bugs, missing features, and upcoming additions

- `createSiteFiles`: There is no way to edit or append a file instead of overriding it wholesale
- `autoinstall`: Need a setup script to download and compile `dnsmasq` into `machdep` directory
- ALL: Linux host OS is planned but not yet supported
- ALL: Windows host OS is specifically unsupported and is unlikely to be supported without external code contributions
- ALL: The code will likely need a total rewrite to make it cleaner, more uniform, and more Pythonic
