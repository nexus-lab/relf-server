#!/usr/bin/env python
# -*- mode: python; encoding: utf-8 -*-
"""Test client vfs."""

import logging
import os
import shutil
import stat


import psutil

# pylint: disable=unused-import,g-bad-import-order
from grr.client import client_plugins
# pylint: enable=unused-import,g-bad-import-order

from grr.client import vfs
from grr.client.vfs_handlers import files
from grr.lib import flags
from grr.lib import utils
from grr.lib.rdfvalues import client as rdf_client
from grr.lib.rdfvalues import paths as rdf_paths
from grr.test_lib import test_lib
from grr.test_lib import vfs_test_lib

# pylint: mode=test


class VFSTest(test_lib.GRRBaseTest):
  """Test the client VFS switch."""

  def GetNumbers(self):
    """Generate a test string."""
    result = ""
    for i in range(1, 1001):
      result += "%s\n" % i

    return result

  def TestFileHandling(self, fd):
    """Test the file like object behaviour."""
    original_string = self.GetNumbers()

    self.assertEqual(fd.size, len(original_string))

    fd.Seek(0)
    self.assertEqual(fd.Read(100), original_string[0:100])
    self.assertEqual(fd.Tell(), 100)

    fd.Seek(-10, 1)
    self.assertEqual(fd.Tell(), 90)
    self.assertEqual(fd.Read(10), original_string[90:100])

    fd.Seek(0, 2)
    self.assertEqual(fd.Tell(), len(original_string))
    self.assertEqual(fd.Read(10), "")
    self.assertEqual(fd.Tell(), len(original_string))

    # Raise if we try to list the contents of a file object.
    self.assertRaises(IOError, lambda: list(fd.ListFiles()))

  def testRegularFile(self):
    """Test our ability to read regular files."""
    path = os.path.join(self.base_path, "morenumbers.txt")
    pathspec = rdf_paths.PathSpec(
        path=path, pathtype=rdf_paths.PathSpec.PathType.OS)
    fd = vfs.VFSOpen(pathspec)

    self.TestFileHandling(fd)

  def testOpenFilehandles(self):
    """Test that file handles are cached."""
    current_process = psutil.Process(os.getpid())
    num_open_files = len(current_process.open_files())

    path = os.path.join(self.base_path, "morenumbers.txt")

    fds = []
    for _ in range(100):
      fd = vfs.VFSOpen(
          rdf_paths.PathSpec(
              path=path, pathtype=rdf_paths.PathSpec.PathType.OS))
      self.assertEqual(fd.read(20), "1\n2\n3\n4\n5\n6\n7\n8\n9\n10")
      fds.append(fd)

    # This should not create any new file handles.
    self.assertTrue(len(current_process.open_files()) - num_open_files < 5)

  def testOpenFilehandlesExpire(self):
    """Test that file handles expire from cache."""
    files.FILE_HANDLE_CACHE = utils.FastStore(max_size=10)

    current_process = psutil.Process(os.getpid())
    num_open_files = len(current_process.open_files())

    path = os.path.join(self.base_path, "morenumbers.txt")
    fd = vfs.VFSOpen(
        rdf_paths.PathSpec(path=path, pathtype=rdf_paths.PathSpec.PathType.OS))

    fds = []
    for filename in fd.ListNames():
      child_fd = vfs.VFSOpen(
          rdf_paths.PathSpec(
              path=os.path.join(path, filename),
              pathtype=rdf_paths.PathSpec.PathType.OS))
      fd.read(20)
      fds.append(child_fd)

    # This should not create any new file handles.
    self.assertTrue(len(current_process.open_files()) - num_open_files < 5)

    # Make sure we exceeded the size of the cache.
    self.assertGreater(fds, 20)

  def testFileCasing(self):
    """Test our ability to read the correct casing from filesystem."""
    try:
      os.lstat(os.path.join(self.base_path, "nUmBeRs.txt"))
      os.lstat(os.path.join(self.base_path, "nuMbErs.txt"))
      # If we reached this point we are on a case insensitive file system
      # and the tests below do not make any sense.
      logging.warning("Case insensitive file system detected. Skipping test.")
      return
    except (IOError, OSError):
      pass

    # Create 2 files with names that differ only in casing.
    with utils.TempDirectory() as temp_dir:
      path1 = os.path.join(temp_dir, "numbers.txt")
      shutil.copy(os.path.join(self.base_path, "numbers.txt"), path1)

      path2 = os.path.join(temp_dir, "numbers.TXT")
      shutil.copy(os.path.join(self.base_path, "numbers.txt.ver2"), path2)

      fd = vfs.VFSOpen(
          rdf_paths.PathSpec(
              path=path1, pathtype=rdf_paths.PathSpec.PathType.OS))
      self.assertEqual(fd.pathspec.Basename(), "numbers.txt")

      fd = vfs.VFSOpen(
          rdf_paths.PathSpec(
              path=path2, pathtype=rdf_paths.PathSpec.PathType.OS))
      self.assertEqual(fd.pathspec.Basename(), "numbers.TXT")

      path = os.path.join(self.base_path, "Numbers.txt")
      fd = vfs.VFSOpen(
          rdf_paths.PathSpec(
              path=path, pathtype=rdf_paths.PathSpec.PathType.OS))
      read_path = fd.pathspec.Basename()

      # The exact file now is non deterministic but should be either of the two:
      if read_path != "numbers.txt" and read_path != "numbers.TXT":
        raise RuntimeError("read path is %s" % read_path)

      # Ensure that the produced pathspec specified no case folding:
      s = fd.Stat()
      self.assertEqual(s.pathspec.path_options,
                       rdf_paths.PathSpec.Options.CASE_LITERAL)

      # Case folding will only occur when requested - this should raise because
      # we have the CASE_LITERAL option:
      pathspec = rdf_paths.PathSpec(
          path=path,
          pathtype=rdf_paths.PathSpec.PathType.OS,
          path_options=rdf_paths.PathSpec.Options.CASE_LITERAL)
      self.assertRaises(IOError, vfs.VFSOpen, pathspec)

  def testTSKFile(self):
    """Test our ability to read from image files."""
    path = os.path.join(self.base_path, "test_img.dd")
    path2 = "Test Directory/numbers.txt"

    p2 = rdf_paths.PathSpec(
        path=path2, pathtype=rdf_paths.PathSpec.PathType.TSK)
    p1 = rdf_paths.PathSpec(path=path, pathtype=rdf_paths.PathSpec.PathType.OS)
    p1.Append(p2)
    fd = vfs.VFSOpen(p1)
    self.TestFileHandling(fd)

  def testTSKFileInode(self):
    """Test opening a file through an indirect pathspec."""
    pathspec = rdf_paths.PathSpec(
        path=os.path.join(self.base_path, "test_img.dd"),
        pathtype=rdf_paths.PathSpec.PathType.OS)
    pathspec.Append(
        pathtype=rdf_paths.PathSpec.PathType.TSK,
        inode=12,
        path="/Test Directory")
    pathspec.Append(
        pathtype=rdf_paths.PathSpec.PathType.TSK, path="numbers.txt")

    fd = vfs.VFSOpen(pathspec)

    # Check that the new pathspec is correctly reduced to two components.
    self.assertEqual(
        fd.pathspec.first.path,
        utils.NormalizePath(os.path.join(self.base_path, "test_img.dd")))
    self.assertEqual(fd.pathspec[1].path, "/Test Directory/numbers.txt")

    # And the correct inode is placed in the final branch.
    self.assertEqual(fd.Stat().pathspec.nested_path.inode, 15)
    self.TestFileHandling(fd)

  def testTSKFileCasing(self):
    """Test our ability to read the correct casing from image."""
    path = os.path.join(self.base_path, "test_img.dd")
    path2 = os.path.join("test directory", "NuMbErS.TxT")

    ps2 = rdf_paths.PathSpec(
        path=path2, pathtype=rdf_paths.PathSpec.PathType.TSK)

    ps = rdf_paths.PathSpec(path=path, pathtype=rdf_paths.PathSpec.PathType.OS)
    ps.Append(ps2)
    fd = vfs.VFSOpen(ps)

    # This fixes Windows paths.
    path = path.replace("\\", "/")
    # The pathspec should have 2 components.

    self.assertEqual(fd.pathspec.first.path, utils.NormalizePath(path))
    self.assertEqual(fd.pathspec.first.pathtype, rdf_paths.PathSpec.PathType.OS)

    nested = fd.pathspec.last
    self.assertEqual(nested.path, u"/Test Directory/numbers.txt")
    self.assertEqual(nested.pathtype, rdf_paths.PathSpec.PathType.TSK)

  def testTSKInodeHandling(self):
    """Test that we can open files by inode."""
    path = os.path.join(self.base_path, "ntfs_img.dd")
    ps2 = rdf_paths.PathSpec(
        inode=65,
        ntfs_type=128,
        ntfs_id=0,
        path="/this/will/be/ignored",
        pathtype=rdf_paths.PathSpec.PathType.TSK)

    ps = rdf_paths.PathSpec(
        path=path, pathtype=rdf_paths.PathSpec.PathType.OS, offset=63 * 512)
    ps.Append(ps2)
    fd = vfs.VFSOpen(ps)

    self.assertEqual(fd.Read(100), "Hello world\n")

    ps2 = rdf_paths.PathSpec(
        inode=65,
        ntfs_type=128,
        ntfs_id=4,
        pathtype=rdf_paths.PathSpec.PathType.TSK)
    ps = rdf_paths.PathSpec(
        path=path, pathtype=rdf_paths.PathSpec.PathType.OS, offset=63 * 512)
    ps.Append(ps2)
    fd = vfs.VFSOpen(ps)

    self.assertEqual(fd.read(100), "I am a real ADS\n")

    # Make sure the size is correct:
    self.assertEqual(fd.Stat().st_size, len("I am a real ADS\n"))

  def testTSKNTFSHandling(self):
    """Test that TSK can correctly encode NTFS features."""
    path = os.path.join(self.base_path, "ntfs_img.dd")
    path2 = "test directory"

    ps2 = rdf_paths.PathSpec(
        path=path2, pathtype=rdf_paths.PathSpec.PathType.TSK)

    ps = rdf_paths.PathSpec(
        path=path, pathtype=rdf_paths.PathSpec.PathType.OS, offset=63 * 512)
    ps.Append(ps2)
    fd = vfs.VFSOpen(ps)

    # This fixes Windows paths.
    path = path.replace("\\", "/")
    listing = []
    pathspecs = []

    for f in fd.ListFiles():
      # Make sure the CASE_LITERAL option is set for all drivers so we can just
      # resend this proto back.
      self.assertEqual(f.pathspec.path_options,
                       rdf_paths.PathSpec.Options.CASE_LITERAL)
      pathspec = f.pathspec.nested_path
      self.assertEqual(pathspec.path_options,
                       rdf_paths.PathSpec.Options.CASE_LITERAL)
      pathspecs.append(f.pathspec)
      listing.append((pathspec.inode, pathspec.ntfs_type, pathspec.ntfs_id))

    # The tsk_fs_attr_type enum:
    tsk_fs_attr_type = rdf_paths.PathSpec.tsk_fs_attr_type

    ref = [(65, tsk_fs_attr_type.TSK_FS_ATTR_TYPE_DEFAULT,
            0), (65, tsk_fs_attr_type.TSK_FS_ATTR_TYPE_NTFS_DATA,
                 4), (66, tsk_fs_attr_type.TSK_FS_ATTR_TYPE_DEFAULT, 0),
           (67, tsk_fs_attr_type.TSK_FS_ATTR_TYPE_DEFAULT, 0)]

    # Make sure that the ADS is recovered.
    self.assertEqual(listing, ref)

    # Try to read the main file
    self.assertEqual(pathspecs[0].nested_path.path, "/Test Directory/notes.txt")
    fd = vfs.VFSOpen(pathspecs[0])
    self.assertEqual(fd.read(1000), "Hello world\n")

    s = fd.Stat()
    self.assertEqual(s.pathspec.nested_path.inode, 65)
    self.assertEqual(s.pathspec.nested_path.ntfs_type, 1)
    self.assertEqual(s.pathspec.nested_path.ntfs_id, 0)

    # Check that the name of the ads is consistent.
    self.assertEqual(pathspecs[1].nested_path.path, "/Test Directory/notes.txt")
    self.assertEqual(pathspecs[1].nested_path.stream_name, "ads")

    # Check that the ADS name is encoded correctly in the AFF4 URN for this
    # file.
    aff4_urn = pathspecs[1].AFF4Path(rdf_client.ClientURN("C.1234567812345678"))
    self.assertEqual(aff4_urn.Basename(), "notes.txt:ads")

    fd = vfs.VFSOpen(pathspecs[1])
    self.assertEqual(fd.read(1000), "I am a real ADS\n")

    # Test that the stat contains the inode:
    s = fd.Stat()
    self.assertEqual(s.pathspec.nested_path.inode, 65)
    self.assertEqual(s.pathspec.nested_path.ntfs_type, 128)
    self.assertEqual(s.pathspec.nested_path.ntfs_id, 4)

  def testNTFSProgressCallback(self):

    self.progress_counter = 0

    def Progress():
      self.progress_counter += 1

    path = os.path.join(self.base_path, "ntfs_img.dd")
    path2 = "test directory"

    ps2 = rdf_paths.PathSpec(
        path=path2, pathtype=rdf_paths.PathSpec.PathType.TSK)

    ps = rdf_paths.PathSpec(
        path=path, pathtype=rdf_paths.PathSpec.PathType.OS, offset=63 * 512)
    ps.Append(ps2)

    vfs.VFSOpen(ps, progress_callback=Progress)

    self.assertTrue(self.progress_counter > 0)

  def testUnicodeFile(self):
    """Test ability to read unicode files from images."""
    path = os.path.join(self.base_path, "test_img.dd")
    path2 = os.path.join(u"???????? ???? ?? ????????", u"????????.txt")

    ps2 = rdf_paths.PathSpec(
        path=path2, pathtype=rdf_paths.PathSpec.PathType.TSK)

    ps = rdf_paths.PathSpec(path=path, pathtype=rdf_paths.PathSpec.PathType.OS)
    ps.Append(ps2)
    fd = vfs.VFSOpen(ps)
    self.TestFileHandling(fd)

  def testListDirectory(self):
    """Test our ability to list a directory."""
    directory = vfs.VFSOpen(
        rdf_paths.PathSpec(
            path=self.base_path, pathtype=rdf_paths.PathSpec.PathType.OS))

    self.CheckDirectoryListing(directory, "morenumbers.txt")

  def testTSKListDirectory(self):
    """Test directory listing in sleuthkit."""
    path = os.path.join(self.base_path, u"test_img.dd")
    ps2 = rdf_paths.PathSpec(
        path=u"???????????? ????????????????????????", pathtype=rdf_paths.PathSpec.PathType.TSK)
    ps = rdf_paths.PathSpec(path=path, pathtype=rdf_paths.PathSpec.PathType.OS)
    ps.Append(ps2)
    directory = vfs.VFSOpen(ps)
    self.CheckDirectoryListing(directory, u"????????????.txt")

  def testRecursiveImages(self):
    """Test directory listing in sleuthkit."""
    p3 = rdf_paths.PathSpec(
        path="/home/a.txt", pathtype=rdf_paths.PathSpec.PathType.TSK)
    p2 = rdf_paths.PathSpec(
        path="/home/image2.img", pathtype=rdf_paths.PathSpec.PathType.TSK)
    p1 = rdf_paths.PathSpec(
        path=os.path.join(self.base_path, "test_img.dd"),
        pathtype=rdf_paths.PathSpec.PathType.OS)
    p2.Append(p3)
    p1.Append(p2)
    f = vfs.VFSOpen(p1)

    self.assertEqual(f.read(3), "yay")

  def testGuessPathSpec(self):
    """Test that we can guess a pathspec from a path."""
    path = os.path.join(self.base_path, "test_img.dd", "home/image2.img",
                        "home/a.txt")

    pathspec = rdf_paths.PathSpec(
        path=path, pathtype=rdf_paths.PathSpec.PathType.OS)

    fd = vfs.VFSOpen(pathspec)
    self.assertEqual(fd.read(3), "yay")

  def testFileNotFound(self):
    """Test that we raise an IOError for file not found."""
    path = os.path.join(self.base_path, "test_img.dd", "home/image2.img",
                        "home/nosuchfile.txt")

    pathspec = rdf_paths.PathSpec(
        path=path, pathtype=rdf_paths.PathSpec.PathType.OS)
    self.assertRaises(IOError, vfs.VFSOpen, pathspec)

  def testGuessPathSpecPartial(self):
    """Test that we can guess a pathspec from a partial pathspec."""
    path = os.path.join(self.base_path, "test_img.dd")
    pathspec = rdf_paths.PathSpec(
        path=path, pathtype=rdf_paths.PathSpec.PathType.OS)
    pathspec.nested_path.path = "/home/image2.img/home/a.txt"
    pathspec.nested_path.pathtype = rdf_paths.PathSpec.PathType.TSK

    fd = vfs.VFSOpen(pathspec)
    self.assertEqual(fd.read(3), "yay")

    # Open as a directory
    pathspec.nested_path.path = "/home/image2.img/home/"

    fd = vfs.VFSOpen(pathspec)

    names = []
    for s in fd.ListFiles():
      # Make sure that the stat pathspec is correct - it should be 3 levels
      # deep.
      self.assertEqual(s.pathspec.nested_path.path, "/home/image2.img")
      names.append(s.pathspec.nested_path.nested_path.path)

    self.assertTrue("home/a.txt" in names)

  def testRegistryListing(self):
    """Test our ability to list registry keys."""
    reg = rdf_paths.PathSpec.PathType.REGISTRY
    with vfs_test_lib.VFSOverrider(reg, vfs_test_lib.FakeRegistryVFSHandler):
      pathspec = rdf_paths.PathSpec(
          pathtype=rdf_paths.PathSpec.PathType.REGISTRY,
          path=("/HKEY_USERS/S-1-5-20/Software/Microsoft"
                "/Windows/CurrentVersion/Run"))

      expected_names = {"MctAdmin": stat.S_IFDIR, "Sidebar": stat.S_IFDIR}
      expected_data = [
          u"%ProgramFiles%\\Windows Sidebar\\Sidebar.exe /autoRun",
          u"%TEMP%\\Sidebar.exe"
      ]

      for f in vfs.VFSOpen(pathspec).ListFiles():
        base, name = os.path.split(f.pathspec.CollapsePath())
        self.assertEqual(base, pathspec.CollapsePath())
        self.assertIn(name, expected_names)
        self.assertIn(f.registry_data.GetValue(), expected_data)

  def CheckDirectoryListing(self, directory, test_file):
    """Check that the directory listing is sensible."""

    found = False
    for f in directory.ListFiles():
      # TSK makes virtual files with $ if front of them
      path = f.pathspec.Basename()
      if path.startswith("$"):
        continue

      # Check the time is reasonable
      self.assertGreater(f.st_mtime, 10000000)
      self.assertGreater(f.st_atime, 10000000)
      self.assertGreater(f.st_ctime, 10000000)

      if path == test_file:
        found = True
        # Make sure its a regular file with the right size
        self.assertTrue(stat.S_ISREG(f.st_mode))
        self.assertEqual(f.st_size, 3893)

    self.assertEqual(found, True)

    # Raise if we try to read the contents of a directory object.
    self.assertRaises(IOError, directory.Read, 5)

  def testVFSVirtualRoot(self):

    # Let's open a file in the virtual root.
    os_root = "os:%s" % self.base_path
    with test_lib.ConfigOverrider({"Client.vfs_virtualroots": [os_root]}):
      # We need to reset the vfs.VFS_VIRTUALROOTS too.
      vfs.VFSInit().Run()

      fd = vfs.VFSOpen(
          rdf_paths.PathSpec(
              path="/morenumbers.txt", pathtype=rdf_paths.PathSpec.PathType.OS))
      data = fd.read(10)
      self.assertEqual(data, "1\n2\n3\n4\n5\n")

    # This should also work with TSK.
    tsk_root = "tsk:%s" % os.path.join(self.base_path, "test_img.dd")
    with test_lib.ConfigOverrider({"Client.vfs_virtualroots": [tsk_root]}):
      vfs.VFSInit().Run()

      image_file_ps = rdf_paths.PathSpec(
          path=u"???????? ???? ?? ????????/????????.txt",
          pathtype=rdf_paths.PathSpec.PathType.TSK)

      fd = vfs.VFSOpen(image_file_ps)

      data = fd.read(10)
      self.assertEqual(data, "1\n2\n3\n4\n5\n")

      # This should not influence vfs handlers other than OS and TSK.
      reg_type = rdf_paths.PathSpec.PathType.REGISTRY
      os_handler = vfs.VFS_HANDLERS[rdf_paths.PathSpec.PathType.OS]
      with vfs_test_lib.VFSOverrider(reg_type, os_handler):
        with self.assertRaises(IOError):
          image_file_ps.pathtype = reg_type
          vfs.VFSOpen(image_file_ps)

  def testFileSizeOverride(self):

    # We assume /dev/null exists and has a 0 size.
    fname = "/dev/null"
    try:
      st = os.stat(fname)
    except OSError:
      self.skipTest("%s not accessible." % fname)
    if st.st_size != 0:
      self.skipTest("%s doesn't have 0 size." % fname)

    pathspec = rdf_paths.PathSpec(
        path=fname, pathtype="OS", file_size_override=100000000)
    fd = vfs.VFSOpen(pathspec)
    self.assertEqual(fd.size, 100000000)

  def testRecursiveListNames(self):
    """Test our ability to walk over a directory tree."""
    path = os.path.join(self.base_path, "a")

    directory = vfs.VFSOpen(
        rdf_paths.PathSpec(path=path, pathtype=rdf_paths.PathSpec.PathType.OS))

    # Test the helper method
    self.assertEqual(directory._GetDepth("/"), 0)
    self.assertEqual(directory._GetDepth("/foo/bar/baz"), 3)
    # Relative paths aren't supported
    with self.assertRaises(RuntimeError):
      directory._GetDepth("foo/bar")
    # Multiple separators are redundant
    self.assertEqual(directory._GetDepth("/////foo///bar//////baz//"), 3)

    # Test the whole thing
    walk_tups_0 = list(directory.RecursiveListNames())
    walk_tups_1 = list(directory.RecursiveListNames(depth=1))
    walk_tups_2 = list(directory.RecursiveListNames(depth=2))
    walk_tups_inf = list(directory.RecursiveListNames(depth=float("inf")))

    self.assertEqual(walk_tups_0, [(path, ["b"], [])])
    self.assertEqual(walk_tups_1, [(path, ["b"], []), ("%s/b" % path,
                                                       ["c", "d"], [])])
    self.assertEqual(walk_tups_2,
                     [(path, ["b"], []), ("%s/b" % path, ["c", "d"], []),
                      ("%s/b/c" % path, [],
                       ["helloc.txt"]), ("%s/b/d" % path, [], ["hellod.txt"])])
    self.assertEqual(walk_tups_inf,
                     [(path, ["b"], []), ("%s/b" % path, ["c", "d"], []),
                      ("%s/b/c" % path, [],
                       ["helloc.txt"]), ("%s/b/d" % path, [], ["hellod.txt"])])

  def testTskRecursiveListNames(self):
    path = os.path.join(self.base_path, u"test_img.dd")
    ps2 = rdf_paths.PathSpec(pathtype=rdf_paths.PathSpec.PathType.TSK)
    ps = rdf_paths.PathSpec(path=path, pathtype=rdf_paths.PathSpec.PathType.OS)
    ps.Append(ps2)
    directory = vfs.VFSOpen(ps)

    walk_tups_0 = list(directory.RecursiveListNames())
    walk_tups_1 = list(directory.RecursiveListNames(depth=1))
    walk_tups_2 = list(directory.RecursiveListNames(depth=2))
    walk_tups_inf = list(directory.RecursiveListNames(depth=float("inf")))

    self.assertEqual(walk_tups_0, [
        (u"/", [
            u"Test Directory", u"glob_test", u"home", u"lost+found",
            u"???????? ???? ?? ????????", u"???????????? ????????????????????????"
        ], []),
    ])

    self.assertEqual(walk_tups_1, [(u"/", [
        u"Test Directory", u"glob_test", u"home", u"lost+found",
        u"???????? ???? ?? ????????", u"???????????? ????????????????????????"
    ], []), (u"/Test Directory", [],
             [u"numbers.txt"]), (u"/glob_test", [u"a"],
                                 []), (u"/home", [u"test"], [u"image2.img"]),
                                   (u"/lost+found", [],
                                    []), (u"/???????? ???? ?? ????????", [],
                                          [u"????????.txt"]), (u"/???????????? ????????????????????????",
                                                           [], [u"????????????.txt"])])

    self.assertEqual(walk_tups_2,
                     [(u"/", [
                         u"Test Directory", u"glob_test", u"home",
                         u"lost+found", u"???????? ???? ?? ????????", u"???????????? ????????????????????????"
                     ], []), (u"/Test Directory", [], [u"numbers.txt"]),
                      (u"/glob_test", [u"a"], []), (u"/glob_test/a", [u"b"],
                                                    []), (u"/home", [u"test"],
                                                          [u"image2.img"]),
                      (u"/home/test", [u".config", u".mozilla"],
                       []), (u"/lost+found", [],
                             []), (u"/???????? ???? ?? ????????", [],
                                   [u"????????.txt"]), (u"/???????????? ????????????????????????", [],
                                                    [u"????????????.txt"])])

    self.assertEqual(walk_tups_inf, [
        (u"/", [
            u"Test Directory", u"glob_test", u"home", u"lost+found",
            u"???????? ???? ?? ????????", u"???????????? ????????????????????????"
        ], []), (u"/Test Directory", [],
                 [u"numbers.txt"]), (u"/glob_test", [u"a"],
                                     []), (u"/glob_test/a", [u"b"], []),
        (u"/glob_test/a/b", [], [u"foo"]), (u"/home", [u"test"], [
            u"image2.img"
        ]), (u"/home/test", [u".config", u".mozilla"],
             []), (u"/home/test/.config", [u"google-chrome"],
                   []), (u"/home/test/.config/google-chrome", [u"Default"],
                         []), (u"/home/test/.config/google-chrome/Default",
                               [u"Cache", u"Extensions"], [u"History"]),
        (u"/home/test/.config/google-chrome/Default/Cache", [], [
            u"data_0", u"data_0", u"data_1", u"data_1", u"data_2", u"data_3",
            u"f_000001", u"f_000001", u"f_000002", u"f_000002", u"f_000003",
            u"f_000003", u"f_000004", u"f_000004", u"f_000005", u"f_000006",
            u"f_000007", u"f_000008", u"f_000009", u"f_00000a", u"f_00000b",
            u"f_00000c", u"f_00000e", u"f_00000f", u"f_000011", u"f_000012",
            u"f_000013", u"f_000014", u"f_000015", u"f_000016", u"f_000017",
            u"f_000018", u"f_00001a", u"f_00001c", u"f_00001d", u"f_00001e",
            u"f_00001f", u"f_000020", u"f_000021", u"f_000023", u"f_000024",
            u"f_000025", u"f_000026", u"f_000027", u"f_000028", u"f_000029",
            u"f_00002c", u"f_00002d", u"f_00002e", u"f_00002f", u"f_000030",
            u"f_000031", u"f_000032", u"f_000034", u"f_000035", u"f_000037",
            u"f_000038", u"f_000039", u"f_00003a", u"f_00003c", u"f_00003d",
            u"index"
        ]), (u"/home/test/.config/google-chrome/Default/Extensions",
             [u"nlbjncdgjeocebhnmkbbbdekmmmcbfjd"],
             []), (u"/home/test/.config/google-chrome/Default/Extensions/"
                   u"nlbjncdgjeocebhnmkbbbdekmmmcbfjd", [u"2.1.3_0"], []),
        (u"/home/test/.config/google-chrome/Default/Extensions/"
         u"nlbjncdgjeocebhnmkbbbdekmmmcbfjd/2.1.3_0", [u"_locales"], [
             u".#testfile.txt", u"manifest.json", u"testfile.txt"
         ]), (u"/home/test/.config/google-chrome/Default/Extensions/"
              u"nlbjncdgjeocebhnmkbbbdekmmmcbfjd/2.1.3_0/_locales", [u"en"],
              []), (u"/home/test/.config/google-chrome/Default/Extensions/"
                    u"nlbjncdgjeocebhnmkbbbdekmmmcbfjd/2.1.3_0/_locales/en", [],
                    [u"messages.json"]), (u"/home/test/.mozilla", [u"firefox"],
                                          []), (u"/home/test/.mozilla/firefox",
                                                [u"adts404t.default"], []),
        (u"/home/test/.mozilla/firefox/adts404t.default", [],
         [u"places.sqlite"]), (u"/lost+found", [],
                               []), (u"/???????? ???? ?? ????????", [],
                                     [u"????????.txt"]), (u"/???????????? ????????????????????????", [],
                                                      [u"????????????.txt"])
    ])


def main(argv):
  vfs.VFSInit()
  test_lib.main(argv)


if __name__ == "__main__":
  flags.StartMain(main)
