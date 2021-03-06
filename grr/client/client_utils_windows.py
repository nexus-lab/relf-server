#!/usr/bin/env python
"""Windows specific utils."""


import ctypes
import exceptions
import logging
import os
import re
import time
import _winreg
import ntsecuritycon
import pywintypes
import win32api
import win32file
import win32security

from google.protobuf import message

from grr import config
from grr.lib import utils
from grr.lib.rdfvalues import flows as rdf_flows
from grr.lib.rdfvalues import paths as rdf_paths

DACL_PRESENT = 1
DACL_DEFAULT = 0


def CanonicalPathToLocalPath(path):
  r"""Converts the canonical paths as used by GRR to OS specific paths.

  Due to the inconsistencies between handling paths in windows we need to
  convert a path to an OS specific version prior to using it. This function
  should be called just before any OS specific functions.

  Canonical paths on windows have:
    - / instead of \.
    - Begin with /X:// where X is the drive letter.

  Args:
    path: A canonical path specification.

  Returns:
    A windows specific path.
  """
  # Account for raw devices
  path = path.replace("/\\", "\\")
  path = path.replace("/", "\\")
  m = re.match(r"\\([a-zA-Z]):(.*)$", path)
  if m:
    path = "%s:\\%s" % (m.group(1), m.group(2).lstrip("\\"))

  return path


def LocalPathToCanonicalPath(path):
  """Converts path from the local system's convention to the canonical."""
  path_components = path.split("/")
  result = []
  for component in path_components:
    # Devices must maintain their \\ so they do not get broken up.
    m = re.match(r"\\\\.\\", component)

    # The component is not special and can be converted as normal
    if not m:
      component = component.replace("\\", "/")

    result.append(component)

  return utils.JoinPath(*result)


def WinChmod(filename, acl_list, user=None):
  """Provide chmod-like functionality for windows.

  Doco links:
    goo.gl/n7YR1
    goo.gl/rDv81
    goo.gl/hDobb

  Args:
    filename: target filename for acl

    acl_list: list of ntsecuritycon acl strings to be applied with bitwise OR.
              e.g. ["FILE_GENERIC_READ", "FILE_GENERIC_WRITE"]

    user: username string. If not specified we use the user we are running as.

  Raises:
    AttributeError: if a bad permission is passed
    RuntimeError: if filename doesn't exist
  """
  if user is None:
    user = win32api.GetUserName()

  if not os.path.exists(filename):
    raise RuntimeError("filename %s does not exist" % filename)

  acl_bitmask = 0
  for acl in acl_list:
    acl_bitmask |= getattr(ntsecuritycon, acl)

  dacl = win32security.ACL()
  win_user, _, _ = win32security.LookupAccountName("", user)

  dacl.AddAccessAllowedAce(win32security.ACL_REVISION, acl_bitmask, win_user)

  security_descriptor = win32security.GetFileSecurity(
      filename, win32security.DACL_SECURITY_INFORMATION)

  # Tell windows to set the acl and mark it as explicitly set
  security_descriptor.SetSecurityDescriptorDacl(DACL_PRESENT, dacl,
                                                DACL_DEFAULT)
  win32security.SetFileSecurity(
      filename, win32security.DACL_SECURITY_INFORMATION, security_descriptor)


def VerifyFileOwner(filename):
  """Verifies that <filename> is owned by the current user."""
  # On   Windows  server   OSs,  files   created  by   users  in   the
  # Administrators group  will be  owned by Administrators  instead of
  # the user  creating the file  so this  check won't work.   Since on
  # Windows GRR  uses its own  temp directory inside  the installation
  # dir, whenever someone  can modify that dir it's  already game over
  # so this check doesn't add much.
  del filename
  return True


def FindProxies():
  """Tries to find proxies by interrogating all the user's settings.

  This function is a modified urillib.getproxies_registry() from the
  standard library. We just store the proxy value in the environment
  for urllib to find it.

  TODO(user): Iterate through all the possible values if one proxy
  fails, in case more than one proxy is specified in different users
  profiles.

  Returns:
    A list of proxies.
  """

  proxies = []
  for i in range(0, 100):
    try:
      sid = _winreg.EnumKey(_winreg.HKEY_USERS, i)
    except exceptions.WindowsError:
      break

    try:
      subkey = (
          sid + "\\Software\\Microsoft\\Windows"
          "\\CurrentVersion\\Internet Settings")

      internet_settings = _winreg.OpenKey(_winreg.HKEY_USERS, subkey)

      proxy_enable = _winreg.QueryValueEx(internet_settings, "ProxyEnable")[0]

      if proxy_enable:
        # Returned as Unicode but problems if not converted to ASCII
        proxy_server = str(
            _winreg.QueryValueEx(internet_settings, "ProxyServer")[0])
        if "=" in proxy_server:
          # Per-protocol settings
          for p in proxy_server.split(";"):
            protocol, address = p.split("=", 1)
            # See if address has a type:// prefix

            if not re.match("^([^/:]+)://", address):
              address = "%s://%s" % (protocol, address)

            proxies.append(address)
        else:
          # Use one setting for all protocols
          if proxy_server[:5] == "http:":
            proxies.append(proxy_server)
          else:
            proxies.append("http://%s" % proxy_server)

      internet_settings.Close()

    except (exceptions.WindowsError, ValueError, TypeError):
      continue

  logging.debug("Found proxy servers: %s", proxies)

  return proxies


def GetRawDevice(path):
  """Resolves the raw device that contains the path.

  Args:
    path: A path to examine.

  Returns:
    A pathspec to read the raw device as well as the modified path to read
    within the raw device. This is usually the path without the mount point.

  Raises:
    IOError: if the path does not exist or some unexpected behaviour occurs.
  """
  path = CanonicalPathToLocalPath(path)
  # Try to expand the shortened paths
  try:
    path = win32file.GetLongPathName(path)
  except pywintypes.error:
    pass

  try:
    mount_point = win32file.GetVolumePathName(path)
  except pywintypes.error as details:
    logging.info("path not found. %s", details)
    raise IOError("No mountpoint for path: %s", path)

  if not path.startswith(mount_point):
    stripped_mp = mount_point.rstrip("\\")
    if not path.startswith(stripped_mp):
      raise IOError("path %s is not mounted under %s" % (path, mount_point))

  corrected_path = LocalPathToCanonicalPath(path[len(mount_point):])
  corrected_path = utils.NormalizePath(corrected_path)

  volume = win32file.GetVolumeNameForVolumeMountPoint(mount_point).rstrip("\\")
  volume = LocalPathToCanonicalPath(volume)

  # The pathspec for the raw volume
  result = rdf_paths.PathSpec(
      path=volume,
      pathtype=rdf_paths.PathSpec.PathType.OS,
      mount_point=mount_point.rstrip("\\"))

  return result, corrected_path


class NannyController(object):
  """Controls communication with the nanny."""

  _service_key = None
  synced = True

  def _GetKey(self):
    """Returns the service key."""
    if self._service_key is None:
      hive = getattr(_winreg, config.CONFIG["Nanny.service_key_hive"])
      path = config.CONFIG["Nanny.service_key"]

      # Don't use _winreg.KEY_WOW64_64KEY since it breaks on Windows 2000
      self._service_key = _winreg.CreateKeyEx(hive, path, 0,
                                              _winreg.KEY_ALL_ACCESS)

    return self._service_key

  def Heartbeat(self):
    """Writes a heartbeat to the registry."""
    try:
      _winreg.SetValueEx(self._GetKey(), "Nanny.heartbeat", 0,
                         _winreg.REG_DWORD, int(time.time()))
    except exceptions.WindowsError, e:
      logging.debug("Failed to heartbeat nanny at %s: %s",
                    config.CONFIG["Nanny.service_key"], e)

  def WriteTransactionLog(self, grr_message):
    """Write the message into the transaction log.

    Args:
      grr_message: A GrrMessage instance.
    """
    grr_message = grr_message.SerializeToString()
    try:
      _winreg.SetValueEx(self._GetKey(), "Transaction", 0, _winreg.REG_BINARY,
                         grr_message)
      NannyController.synced = False
    except exceptions.WindowsError:
      pass

  def SyncTransactionLog(self):
    if not NannyController.synced:
      _winreg.FlushKey(self._GetKey())
      NannyController.synced = True

  def CleanTransactionLog(self):
    """Wipes the transaction log."""
    try:
      _winreg.DeleteValue(self._GetKey(), "Transaction")
      NannyController.synced = False
    except exceptions.WindowsError:
      pass

  def GetTransactionLog(self):
    """Return a GrrMessage instance from the transaction log or None."""
    try:
      value, reg_type = _winreg.QueryValueEx(self._GetKey(), "Transaction")
    except exceptions.WindowsError:
      return

    if reg_type != _winreg.REG_BINARY:
      return

    try:
      return rdf_flows.GrrMessage.FromSerializedString(value)
    except message.Error:
      return

  def GetNannyStatus(self):
    try:
      value, _ = _winreg.QueryValueEx(self._GetKey(), "Nanny.status")
    except exceptions.WindowsError:
      return None

    return value

  def GetNannyMessage(self):
    try:
      value, _ = _winreg.QueryValueEx(self._GetKey(), "Nanny.message")
    except exceptions.WindowsError:
      return None

    return value

  def ClearNannyMessage(self):
    """Wipes the nanny message."""
    try:
      _winreg.DeleteValue(self._GetKey(), "Nanny.message")
      NannyController.synced = False
    except exceptions.WindowsError:
      pass

  def StartNanny(self):
    """Not used for the Windows nanny."""

  def StopNanny(self):
    """Not used for the Windows nanny."""


class Kernel32(object):
  _kernel32 = None

  def __init__(self):
    if not Kernel32._kernel32:
      Kernel32._kernel32 = ctypes.windll.LoadLibrary("Kernel32.dll")

  @property
  def kernel32(self):
    return self._kernel32


def KeepAlive():

  es_system_required = 0x00000001

  kernel32 = Kernel32().kernel32
  kernel32.SetThreadExecutionState(ctypes.c_int(es_system_required))


def RtlGetVersion(os_version_info_struct):
  """Wraps the lowlevel RtlGetVersion routine.

  Args:
    os_version_info_struct: instance of either a RTL_OSVERSIONINFOW structure
                            or a RTL_OSVERSIONINFOEXW structure,
                            ctypes.Structure-wrapped, with the
                            dwOSVersionInfoSize field preset to
                            ctypes.sizeof(self).

  Raises:
    WindowsError: if the underlaying routine fails.

  See: https://msdn.microsoft.com/en-us/library/
  windows/hardware/ff561910(v=vs.85).aspx .
  """
  rc = ctypes.windll.Ntdll.RtlGetVersion(ctypes.byref(os_version_info_struct))
  if rc != 0:
    raise exceptions.WindowsError("Getting Windows version failed.")


class RtlOSVersionInfoExw(ctypes.Structure):
  """Wraps the lowlevel RTL_OSVERSIONINFOEXW struct.

  See: https://msdn.microsoft.com/en-us/library/
  windows/hardware/ff563620(v=vs.85).aspx .
  """
  _fields_ = [("dwOSVersionInfoSize", ctypes.c_ulong), ("dwMajorVersion",
                                                        ctypes.c_ulong),
              ("dwMinorVersion",
               ctypes.c_ulong), ("dwBuildNumber",
                                 ctypes.c_ulong), ("dwPlatformId",
                                                   ctypes.c_ulong),
              ("szCSDVersion",
               ctypes.c_wchar * 128), ("wServicePackMajor",
                                       ctypes.c_ushort), ("wServicePackMinor",
                                                          ctypes.c_ushort),
              ("wSuiteMask", ctypes.c_ushort), ("wProductType",
                                                ctypes.c_byte), ("wReserved",
                                                                 ctypes.c_byte)]

  def __init__(self, **kwargs):
    kwargs["dwOSVersionInfoSize"] = ctypes.sizeof(self)
    super(RtlOSVersionInfoExw, self).__init__(**kwargs)


def KernelVersion():
  """Gets the kernel version as string, eg. "5.1.2600".

  Returns:
    The kernel version, or "unknown" in the case of failure.
  """
  rtl_osversioninfoexw = RtlOSVersionInfoExw()
  try:
    RtlGetVersion(rtl_osversioninfoexw)
  except exceptions.WindowsError:
    return "unknown"

  return "%d.%d.%d" % (rtl_osversioninfoexw.dwMajorVersion,
                       rtl_osversioninfoexw.dwMinorVersion,
                       rtl_osversioninfoexw.dwBuildNumber)


def AddStatEntryExtFlags(stat_entry, stat_object):
  """Does nothing.

  This is kept for compatibility with other platform-specific version of this
  function.

  Args:
    stat_entry: An `StatEntry` object to fill-in.
    stat_object: An object representing results of the `os.stat` call.
  """
  del stat_entry  # Unused on Windows.
  del stat_object  # Unused on Windows.
