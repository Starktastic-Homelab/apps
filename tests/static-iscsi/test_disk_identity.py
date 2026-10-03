import unittest
from disk_identity import data_disk

class DiskIdentityTests(unittest.TestCase):
    def test_reordered_names_use_serial(self):
        disks = [dict(name="sda", serial="ISCSILABDATA", size=16*1024**3, pool=None), dict(name="sdb", serial="ISCSILABBOOT", size=16*1024**3, pool=None)]
        self.assertEqual(data_disk(disks, ["sdb"]), "sda")

    def test_refuses_boot_even_with_expected_serial(self):
        with self.assertRaises(ValueError):
            data_disk([dict(name="sda", serial="ISCSILABDATA", size=16*1024**3, pool=None)], ["sda"])

    def test_refuses_ambiguous_missing_in_use_or_wrong_size(self):
        disk = dict(name="sda", serial="ISCSILABDATA", size=16*1024**3, pool=None)
        for disks in ([], [disk, dict(disk, name="sdc")], [dict(disk, pool="existing")], [dict(disk, size=1024)]):
            with self.subTest(disks=disks), self.assertRaises(ValueError):
                data_disk(disks, ["sdb"])
