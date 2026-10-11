import copy,json,pathlib,unittest
import identity

class CapacityTests(unittest.TestCase):
 def setUp(self):
  root=pathlib.Path(__file__).parent
  fixture=json.loads((root/'native-fixture.json').read_text())
  self.record=next(r for r in fixture['records'] if r['service']=='service-a')
  self.state=fixture['state']
 def test_old_and_planned_capacity_reconcile_without_allocation(self):
  target=self.record['bytes']+1024**3
  self.assertEqual(identity.reconcile_capacity(self.record,self.state,target)['bytes'],self.record['bytes'])
  next(d for d in self.state['datasets'] if d['id']==self.record['dataset'])['volsize']['parsed']=target
  self.assertEqual(identity.reconcile_capacity(self.record,self.state,target)['bytes'],target)
 def test_unplanned_capacity_or_replaced_volume_refused(self):
  target=self.record['bytes']+1024**3
  ds=next(d for d in self.state['datasets'] if d['id']==self.record['dataset'])
  ds['volsize']['parsed']=target+1024**3
  with self.assertRaises(ValueError):identity.reconcile_capacity(self.record,self.state,target)
  ds['volsize']['parsed']=target;ds['guid']['value']='replacement'
  with self.assertRaises(ValueError):identity.reconcile_capacity(self.record,self.state,target)
 def test_shrink_intent_refused(self):
  with self.assertRaises(ValueError):identity.reconcile_capacity(self.record,self.state,self.record['bytes'])
