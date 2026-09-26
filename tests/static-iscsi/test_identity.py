import copy, json, pathlib, unittest
from identity import verify_native

FIXTURE=json.loads(pathlib.Path(__file__).with_name("native-fixture.json").read_text())

class NativeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.record=copy.deepcopy(FIXTURE["records"][0])
        self.state=copy.deepcopy(FIXTURE["state"])

    def test_recorded_native_identity_passes(self):
        verify_native(self.record,self.state)

    def test_replacement_redirect_or_maintenance_drift_is_rejected(self):
        cases=[("pools","guid","replaced"),("datasets","guid",{"value":"replaced"}),
               ("datasets","volsize",{"parsed":256*1024**2}),
               ("extents","disk","zvol/iscsi_lab/volumes/service-b"),
               ("extents","serial","replaced"),("extents","naa","replaced"),
               ("extents","enabled",False),("extents","ro",True),("extents","insecure_tpc",True),
               ("targets","name","redirected"),("targets","groups",[]),
               ("targets","auth_networks",[]),("mappings","extent",2),("mappings","lunid",1),
               ("portals","listen",[{"ip":"0.0.0.0","port":3260}]),
               ("initiators","initiators",[])]
        for section,field,value in cases:
            state=copy.deepcopy(self.state);state[section][0][field]=value
            with self.subTest(section=section,field=field),self.assertRaises(ValueError):
                verify_native(self.record,state)

    def test_missing_and_ambiguous_objects_are_rejected(self):
        for section in ("pools","datasets","extents","targets","mappings","portals","initiators"):
            for entries in ([],[self.state[section][0]]*2):
                state=copy.deepcopy(self.state);state[section]=entries
                with self.subTest(section=section,entries=len(entries)),self.assertRaises(ValueError):
                    verify_native(self.record,state)

    def test_auth_downgrade_and_broad_initiators_are_rejected(self):
        for field,value in (("authmethod","NONE"),("auth",None),("initiator",None)):
            state=copy.deepcopy(self.state);state["targets"][0]["groups"][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                verify_native(self.record,state)
        self.state["initiators"][0]["initiators"].append("iqn.foreign.writer")
        with self.assertRaises(ValueError):verify_native(self.record,self.state)

    def test_changed_iqn_basename_is_rejected(self):
        self.state["basename"]="iqn.foreign"
        with self.assertRaises(ValueError):verify_native(self.record,self.state)
