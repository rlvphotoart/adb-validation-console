import os
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from platform_tools import PlatformToolsManager, parse_devices
from command_library import COMMANDS
from adb_validation_console import classify_manual, filter_lines

class CoreTests(unittest.TestCase):
    def fake(self, folder):
        p=folder/'adb.exe'
        p.write_text('#!/usr/bin/env python3\nimport os,sys,time\n'
                     'if "sleep" in sys.argv: time.sleep(4)\n'
                     'print("CWD="+os.getcwd())\nprint("ARGS="+repr(sys.argv[1:]))\n')
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
        return p

    def test_discovery_order_and_arguments(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); source=root/'source'; cwd=root/'cwd'; configured=root/'configured'
            for p in (source,cwd,configured): p.mkdir()
            first=self.fake(source); self.fake(cwd); self.fake(configured)
            manager=PlatformToolsManager(str(configured),source=str(source/'app.py'),cwd=str(cwd),which=lambda _:None)
            self.assertEqual(manager.detect(),first.resolve())
            self.assertEqual(manager.argv(['shell','getprop','ro.build.type'],'10.19.229.1:5555'),
                             [str(first.resolve()),'-s','10.19.229.1:5555','shell','getprop','ro.build.type'])
            if os.name == 'nt':
                return  # Windows cannot execute a shebang script named adb.exe.
            result=manager.run(['shell','getprop','ro.build.type'],'SERIAL WITH SPACE')
            self.assertEqual(result.returncode,0)
            self.assertIn('CWD='+str(source.resolve()),result.stdout)
            self.assertIn("'SERIAL WITH SPACE'",result.stdout)

    @unittest.skipIf(os.name == 'nt', 'Requires an executable POSIX shebang fixture')
    def test_timeout_and_cancel(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); self.fake(folder)
            manager=PlatformToolsManager(source=str(folder/'app.py'),cwd=root,which=lambda _:None); manager.detect()
            self.assertTrue(manager.run(['sleep'],timeout=.2).timed_out)
            event=threading.Event(); timer=threading.Timer(.2,event.set); timer.start()
            result=manager.run(['sleep'],timeout=5,stop=event)
            self.assertNotEqual(result.returncode,0)
            self.assertLess(result.duration,2)

    def test_subprocess_arguments_with_mock_adb(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); adb=folder/'adb.exe'; adb.write_bytes(b'MZ')
            manager=PlatformToolsManager(source=str(folder/'app.py'),cwd=root,which=lambda _:None)
            self.assertEqual(manager.detect(),adb.resolve())
            process=Mock(returncode=0)
            process.communicate.return_value=(b'ok\n',b'')
            with patch('platform_tools.subprocess.Popen',return_value=process) as launch:
                result=manager.run(['shell','getprop','ro.build.type'],'SERIAL WITH SPACE')
            self.assertEqual(result.stdout,'ok\n')
            self.assertEqual(launch.call_args.args[0],
                             [str(adb.resolve()),'-s','SERIAL WITH SPACE','shell','getprop','ro.build.type'])
            self.assertEqual(launch.call_args.kwargs['cwd'],folder.resolve())

    def test_device_parse_filter_and_safety(self):
        data='List of devices attached\nUSB123\tdevice product:x model:y\n10.0.0.1:5555\tunauthorized\n'
        devices=parse_devices(data)
        self.assertEqual([(x.serial,x.state) for x in devices],[('USB123','device'),('10.0.0.1:5555','unauthorized')])
        self.assertEqual(filter_lines('touch event\nbluetooth event','touch'),'touch event')
        self.assertEqual(classify_manual(['shell','pm','clear','com.test.app']),'DESTRUCTIVE')
        self.assertEqual(classify_manual(['shell','setenforce','0']),'BLOCKED')
        self.assertIn('Dumpsys audio',COMMANDS)

if __name__=='__main__': unittest.main()
