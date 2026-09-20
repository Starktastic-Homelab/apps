import unittest
from guard import ShutdownGate, owns_vm

GIB = 1024**3
MANIFEST = {'marker': 'iscsi-lab-20260920-a1b2', 'vms': {'910': {
    'name': 'iscsi-lab-nas-a1b2', 'uuid': 'd38aa113-32cd-4634-82b0-cd26a63cda20', 'memory': 8192}}}
CONFIG = {'name': 'iscsi-lab-nas-a1b2', 'smbios1': 'uuid=d38aa113-32cd-4634-82b0-cd26a63cda20',
          'tags': 'iscsi-lab-20260920-a1b2', 'memory': '8192', 'onboot': '0'}


class GuardTests(unittest.TestCase):
    def test_exact_owner(self):
        self.assertTrue(owns_vm(910, CONFIG, MANIFEST))

    def test_production_id_rejected_even_if_manifest_lies(self):
        forged = {'marker': MANIFEST['marker'], 'vms': {'200': MANIFEST['vms']['910']}}
        self.assertFalse(owns_vm(200, CONFIG, forged))

    def test_reused_id_wrong_uuid_name_or_marker_rejected(self):
        for key in ('name', 'smbios1', 'tags'):
            self.assertFalse(owns_vm(910, {**CONFIG, key: 'foreign'}, MANIFEST))
        self.assertFalse(owns_vm(911, CONFIG, MANIFEST))

    def test_sustained_low_memory(self):
        gate = ShutdownGate(3)
        self.assertIsNone(gate.update(0, 5*GIB, 3, True, 0))
        self.assertIsNone(gate.update(29, 5*GIB, 3, True, 0))
        self.assertEqual(gate.update(30, 5*GIB, 3, True, 0), 'host-memory')

    def test_recovery_resets_timer(self):
        gate = ShutdownGate(0)
        for now, available in [(0, 5*GIB), (29, 6*GIB), (30, 5*GIB), (59, 5*GIB)]:
            self.assertIsNone(gate.update(now, available, 0, True, 0))
        self.assertEqual(gate.update(60, 5*GIB, 0, True, 0), 'host-memory')

    def test_oom_or_monitor_fault_stops(self):
        self.assertEqual(ShutdownGate(2).update(0, 20*GIB, 3, True, 0), 'host-oom')
        self.assertEqual(ShutdownGate(2).update(0, 20*GIB, 2, False, 0), 'production-health')
        self.assertEqual(ShutdownGate(2).update(0, 20*GIB, 2, None, 91), 'monitor-stale')

    def test_healthy_does_not_stop(self):
        self.assertIsNone(ShutdownGate(2).update(999, 8*GIB, 2, True, 0))


class ShutdownSafetyTests(unittest.TestCase):
    def test_foreign_vm_never_receives_shutdown(self):
        from unittest.mock import patch
        import guard
        with patch.object(guard, 'vm_config', return_value={**CONFIG, 'tags': 'foreign'}), patch.object(guard, 'run') as run:
            guard.stop_owned(MANIFEST)
        run.assert_not_called()

    def test_identity_change_prevents_force_stop(self):
        from unittest.mock import patch
        import guard
        def config(vmid):
            return CONFIG if vmid == 910 else None
        calls=[]
        def command(args, timeout=15):
            calls.append(args)
            if args[1]=='shutdown':
                raise guard.subprocess.TimeoutExpired(args, timeout)
            return 'status: running'
        configs=[None,None,None,CONFIG,{**CONFIG,'smbios1':'uuid=foreign'}]
        with patch.object(guard,'vm_config',side_effect=configs), patch.object(guard,'run',side_effect=command):
            with self.assertRaisesRegex(RuntimeError,'identity changed'):
                guard.stop_owned(MANIFEST)
        self.assertFalse(any(x[1]=='stop' for x in calls))


class ConfigSectionTests(unittest.TestCase):
    def test_cloudinit_and_snapshot_sections_cannot_override_live_identity(self):
        from unittest.mock import patch
        from guard import vm_config
        raw='name: current\nsmbios1: uuid=current\nnet0: live,link_down=1\n\n[special:cloudinit]\nnet0: old\n\n[snapshot]\nname: old\nsmbios1: uuid=old\n'
        with patch('pathlib.Path.exists',return_value=True),patch('pathlib.Path.read_text',return_value=raw):
            self.assertEqual(vm_config(913)['name'],'current')
            self.assertEqual(vm_config(913)['net0'],'live,link_down=1')


if __name__ == '__main__':
    unittest.main()
