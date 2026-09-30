import shlex
import os
import stat
import tempfile
import unittest
from pathlib import Path
from platform_tools import PlatformToolsManager
from remote_browser import child_path, display_size, list_command, normalize_remote_path, parent_path, parse_long_listing, safe_push_target

class BrowserTests(unittest.TestCase):
    def test_paths_and_remote_shell_quoting(self):
        path="/sdcard/My Folder/a'b;$(touch bad)"
        self.assertEqual(shlex.split(list_command(path)[1]),['ls','-la','--',path+'/'])
        self.assertEqual(normalize_remote_path('/sdcard/Download/../DCIM'),'/sdcard/DCIM')
        self.assertEqual(child_path('/sdcard','My File.txt'),'/sdcard/My File.txt')
        self.assertEqual(parent_path('/sdcard/Download'),'/sdcard')
        with self.assertRaises(ValueError): normalize_remote_path('relative/path')
        with self.assertRaises(ValueError): child_path('/sdcard','../other')
        self.assertTrue(safe_push_target('/sdcard/Download/'))
        self.assertTrue(safe_push_target('/data/local/tmp/report.txt'))
        self.assertFalse(safe_push_target('/factory'))
        self.assertFalse(safe_push_target('/system/etc'))

    def test_android_listing_and_symlink(self):
        output=('total 12\n'
                'drwxrwx--- 2 root sdcard_rw 4096 2026-09-30 17:23 Download\n'
                '-rw-rw---- 1 root sdcard_rw 1536 2026-09-30 17:24 validation notes.txt\n'
                'lrwxrwxrwx 1 root root 8 Sep 30 17:25 Shared -> /sdcard/Download\n')
        entries,skipped=parse_long_listing(output,'/sdcard')
        self.assertEqual(skipped,[])
        self.assertEqual([e.name for e in entries],['Download','Shared','validation notes.txt'])
        self.assertEqual(entries[0].kind,'Folder')
        self.assertEqual(entries[1].target,'/sdcard/Download')
        self.assertEqual(entries[2].path,'/sdcard/validation notes.txt')
        self.assertEqual(display_size(entries[2].size),'1.5 KB')

    def test_unparseable_lines_are_reported(self):
        entries,skipped=parse_long_listing('unrecognized output\n','/sdcard')
        self.assertEqual(entries,[])
        self.assertEqual(skipped,['unrecognized output'])

    @unittest.skipIf(os.name == 'nt', 'Requires an executable POSIX shebang fixture')
    def test_listing_through_fake_adb(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)
            adb=folder/'adb.exe'
            adb.write_text('#!/usr/bin/env python3\nimport sys\n'
                           'assert sys.argv[1:4] == ["-s", "SIM-001", "shell"]\n'
                           'assert sys.argv[4] == "ls -la -- /sdcard/"\n'
                           'print("drwxrwx--- 2 root sdcard_rw 4096 2026-09-30 17:23 Download")\n')
            adb.chmod(adb.stat().st_mode | stat.S_IXUSR)
            manager=PlatformToolsManager(source=str(folder/'app.py'),cwd=root,which=lambda _:None)
            manager.detect()
            result=manager.run(list_command('/sdcard'),serial='SIM-001')
            self.assertEqual(result.returncode,0,result.stderr)
            entries,skipped=parse_long_listing(result.stdout,'/sdcard')
            self.assertEqual((len(entries),len(skipped),entries[0].path),(1,0,'/sdcard/Download'))

if __name__=='__main__': unittest.main()
