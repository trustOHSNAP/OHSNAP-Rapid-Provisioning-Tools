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
# iokitBridge.py #
##################


# STANDARD LIBRARIES
import ctypes
from ctypes import util
from ctypes import *


#
# Map libraries' C objects to Python
#
# xnu and IOKit
#   Typedefs
io_iterator_t = c_void_p
io_iterator_t_ptr = c_void_p
io_name_t = c_void_p
io_object_t = c_void_p
io_registry_entry_t = c_void_p
IOOptionBits = c_void_p
kern_return_t = c_int
mach_port_t = c_void_p
#   Constants
k_io_name_t_buffer_length = 128
#   Macros
def IOServicePlane():
    return IOSTR("IOService")
#
# CoreFoundation
#   Typedefs
Boolean = c_bool
CFAllocatorRef = c_void_p
CFBooleanRef = c_void_p
CFDictionaryRef = c_void_p
CFIndex = c_long
CFMutableDictionaryRef = c_void_p
CFNumberRef = c_void_p
CFNumberType = CFIndex
CFStringEncoding = c_ulong
CFStringRef = c_void_p
CFTypeRef = c_void_p
#   Constants
kCFStringEncodingASCII = 0x0600
kCFStringEncodingUTF8 = 0x08000100
kCFNumberLongType = 10
kCFNumberLongLongType = 11


#
# CLASSES
#
def InitIOKitBridge():
    global iokit
    global cf
    global kIOMasterPortDefault
    
    iokit = ctypes.cdll.LoadLibrary(ctypes.util.find_library('IOKit'))
    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library('CoreFoundation'))

    kIOMasterPortDefault = ctypes.c_void_p.in_dll(iokit, "kIOMasterPortDefault")

    #
    # Map C function prototypes to Python ctypes spec
    #
    
    # CFMutableDictionaryRef IOServiceMatching(const char *name)
    iokit.IOServiceMatching.restype = CFMutableDictionaryRef
    iokit.IOServiceMatching.argtypes = [c_char_p]

    # kern_return_t IOServiceGetMatchingServices(mach_port_t mainPort, CFDictionaryRef matching, io_iterator_t *existing)
    iokit.IOServiceGetMatchingServices.restype = kern_return_t
    iokit.IOServiceGetMatchingServices.argtypes = [mach_port_t, CFDictionaryRef, io_iterator_t_ptr]

    # io_object_t IOIteratorNext(io_iterator_t iterator)
    iokit.IOIteratorNext.restype = io_object_t
    iokit.IOIteratorNext.argtypes = [io_iterator_t]

    # CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t entry, CFStringRef key, CFAllocatorRef allocator, IOOptionBits options)
    iokit.IORegistryEntryCreateCFProperty.restype = CFTypeRef
    iokit.IORegistryEntryCreateCFProperty.argtypes = [io_registry_entry_t, CFStringRef, CFAllocatorRef, IOOptionBits]
    
    # kern_return_t IORegistryEntryGetNameInPlane(io_registry_entry_t entry, const io_name_t plane, io_name_t name)
    iokit.IORegistryEntryGetNameInPlane.restype = kern_return_t
    iokit.IORegistryEntryGetNameInPlane.argtypes = [io_registry_entry_t, io_name_t, io_name_t]

    # CFStringRef CFStringCreateWithCString(CFAllocatorRef alloc, const char *cStr, CFStringEncoding encoding)
    cf.CFStringCreateWithCString.restype = CFStringRef
    cf.CFStringCreateWithCString.argtypes = [CFAllocatorRef, c_char_p, CFStringEncoding]

    # CFIndex CFStringGetLength(CFStringRef theString)
    cf.CFStringGetLength.restype = CFIndex
    cf.CFStringGetLength.argtypes = [CFStringRef]
    
    # Boolean CFStringGetCString(CFStringRef theString, char *buffer, CFIndex bufferSize, CFStringEncoding encoding)
    cf.CFStringGetCString.restype = Boolean
    cf.CFStringGetCString.argtypes = [CFStringRef, c_char_p, CFIndex, CFStringEncoding]
    
    # Boolean CFNumberGetValue(CFNumberRef number, CFNumberType theType, void *valuePtr)
    cf.CFNumberGetValue.restype = Boolean
    cf.CFNumberGetValue.argtypes = [CFNumberRef, CFNumberType, c_void_p]

    # Boolean CFBooleanGetValue(CFBooleanRef boolean)
    cf.CFBooleanGetValue.restype = Boolean
    cf.CFBooleanGetValue.argtypes = [CFBooleanRef]
    
    return kIOMasterPortDefault
    

#
# METHODS
#
def IOSTR(string):
    buffer = ctypes.create_string_buffer(k_io_name_t_buffer_length)


def CFSTR(string):
    return cf.CFStringCreateWithCString(None, string.encode('UTF-8'), kCFStringEncodingUTF8)


def stringFromCFString(cfstr):
    length = cf.CFStringGetLength(cfstr)
    buffer = ctypes.create_string_buffer(length)
    cf.CFStringGetCString(cfstr, buffer, length + 1, kCFStringEncodingUTF8)
    return buffer.value.decode('UTF-8')


def longLongFromCFNumber(cfnum):
    ll = c_longlong()
    cf.CFNumberGetValue(cfnum, kCFNumberLongLongType, pointer(ll))
    return ll.value


def boolFromCFBoolean(cfbool):
    return cf.CFBooleanGetValue(cfbool)


def IOGetProperty(entry, key):
    return iokit.IORegistryEntryCreateCFProperty(entry, key, None, None)


def iokitGetMountedRemovableDevices():
    global iokit
    global cf
    global kIOMasterPortDefault

    devices = list()

    iokitMasterPort = kIOMasterPortDefault

    iterator = c_void_p()

    response = iokit.IOServiceGetMatchingServices(
        iokitMasterPort,
        iokit.IOServiceMatching(b'IOMedia'),
        ctypes.byref(iterator)
    )
    
    bsdNamePropKey = CFSTR("BSD Name")
    wholeDiskPropKey = CFSTR("Whole")
    ejectablePropKey = CFSTR("Ejectable")
    sizePropKey = CFSTR("Size")

    while (entry := iokit.IOIteratorNext(iterator)) != None :
        bsdNameCFStr = IOGetProperty(entry, bsdNamePropKey)
        bsdName = stringFromCFString(bsdNameCFStr)

        wholeDiskCFBool = IOGetProperty(entry, wholeDiskPropKey)
        wholeDisk = boolFromCFBoolean(wholeDiskCFBool)

        ejectableCFBool = IOGetProperty(entry, ejectablePropKey)
        ejectable = boolFromCFBoolean(ejectableCFBool)

        if wholeDisk and ejectable:
            buffer = ctypes.create_string_buffer(k_io_name_t_buffer_length)
            iokit.IORegistryEntryGetNameInPlane(entry, IOServicePlane(), buffer)
            name = buffer.value.decode('UTF-8')
            
            sizeCFNum = IOGetProperty(entry, sizePropKey)
            size = longLongFromCFNumber(sizeCFNum)

            deviceInfo = {
                'name': name,
                'node': bsdName,
                'size': size
            }

            devices.append(deviceInfo)

    return devices
    

InitIOKitBridge()
