"""Probes must never change or disconnect sessions owned by CSI."""
import io
import json
import pathlib
import runpy
import subprocess
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parent
SCRIPTS = ('initiator_guest.py', 'grow_guest.py')
RECORD = {'portal': '127.0.0.1:3260', 'iqn': 'iqn.2026-09.invalid:session-test',
          'lun': 0, 'chap': {'user': 'test', 'secret': 'synthetic'}}


class SessionOwnershipTests(unittest.TestCase):
    def exercise(self, script, existing=False, login=0):
        calls = []

        def command(args, **kwargs):
            calls.append(args)
            if args == ['iscsiadm', '-m', 'session']:
                output = 'tcp: [7] 127.0.0.1:3260,1 ' + RECORD['iqn'] + ' (non-flash)'
                return subprocess.CompletedProcess(args, 0 if existing else 21,
                                                   output if existing else '', '')
            return subprocess.CompletedProcess(args, login if '--login' in args else 0, '', '')

        # The invented by-path device does not exist. A newly created probe session
        # therefore fails its device check, exercising the cleanup path safely.
        with patch('sys.stdin', io.StringIO(json.dumps(RECORD))), \
             patch('subprocess.run', side_effect=command), patch('time.sleep'):
            with self.assertRaises(AssertionError):
                runpy.run_path(str(ROOT / script), run_name='__main__')
        return calls

    def test_existing_session_is_rejected_without_updates_or_logout(self):
        for script in SCRIPTS:
            with self.subTest(script=script):
                calls = self.exercise(script, existing=True, login=15)
                self.assertEqual(calls, [['iscsiadm', '-m', 'session']])

    def test_login_race_does_not_logout_an_existing_session(self):
        for script in SCRIPTS:
            with self.subTest(script=script):
                calls = self.exercise(script, login=15)
                self.assertFalse(any('--logout' in args for args in calls))

    def test_owned_session_is_cleaned_up_when_device_check_fails(self):
        for script in SCRIPTS:
            with self.subTest(script=script):
                calls = self.exercise(script, login=0)
                self.assertEqual(sum('--logout' in args for args in calls), 1)
