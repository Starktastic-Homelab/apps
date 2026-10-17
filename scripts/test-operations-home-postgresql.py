#!/usr/bin/env python3
"""Data-loss regression checks for the two pinned native database providers."""
import datetime,importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('migration_data',Path(__file__).parent/'operations-home-postgresql/data.py');data=importlib.util.module_from_spec(spec);spec.loader.exec_module(data)
class Preservation(unittest.TestCase):
 def test_crowdsec_only_source_nanoseconds_truncate(self):
  self.assertEqual(data.normalize('crowdsec','2026-10-17T11:30:25.123456789+02:00','timestamp with time zone',True),'2026-10-17T09:30:25.123456+00:00')
  with self.assertRaises(ValueError):data.normalize('crowdsec','2026-10-17T09:30:25.123456789Z','timestamp with time zone',False)
 def test_excalidash_milliseconds_and_native_text_equal(self):
  self.assertEqual(data.normalize('excalidash',1001,'timestamp without time zone',True),'1970-01-01T00:00:01.001000')
  self.assertEqual(data.normalize('excalidash','1970-01-01 00:00:01.001','timestamp without time zone',True),'1970-01-01T00:00:01.001000')
  with self.assertRaises(ValueError):data.normalize('excalidash','2026-10-17T11:30:25.123456789','timestamp without time zone',True)
 def test_native_timezone_and_invalid_dates_refused(self):
  for v in ('2026-10-17 00:00:00','2026-19-45T00:00:00Z','nonsense'):
   with self.subTest(v=v),self.assertRaises(ValueError):data.normalize('crowdsec',v,'timestamp with time zone',False)
 def test_text_binary_null_and_boolean_preserved(self):
  self.assertEqual(data.normalize('excalidash',b'\x00\xff','bytea',True),('bytes','00ff'))
  self.assertIsNone(data.normalize('excalidash',None,'text',True))
  self.assertEqual(data.normalize('excalidash',1,'boolean',True),True)
  for value in ('a\x00b','\ud800'):
   with self.assertRaises(ValueError):data.normalize('excalidash',value,'text',True)
  with self.assertRaises(ValueError):data.normalize('excalidash',2,'boolean',True)
 def test_integer_and_real_loss_refused(self):
  for value,kind in ((2**31,'integer'),(True,'bigint'),(0.1,'real'),(float('nan'),'double precision')):
   with self.subTest(kind=kind),self.assertRaises(ValueError):data.normalize('crowdsec',value,kind,True)
  self.assertEqual(data.normalize('crowdsec',0.5,'real',True),('float','0x1.0000000000000p-1'))
 def test_integer_to_double_must_be_exact(self):
  with self.assertRaises(ValueError):data.normalize('crowdsec',2**53+1,'double precision',True)
  self.assertEqual(data.normalize('crowdsec',2**53,'double precision',True),('float',float(2**53).hex()))
 def test_json_numbers_keys_and_duplicate_rejection(self):
  a=data.normalize('crowdsec','{"a":1.00,"b":[null,true,"x"]}','jsonb',True)
  b=data.normalize('crowdsec','{"b":[null,true,"x"],"a":1}','jsonb',False)
  self.assertEqual(a,b)
  with self.assertRaises(ValueError):data.normalize('crowdsec','{"a":1,"a":2}','jsonb',True)
 def test_crowdsec_native_json_blob_is_strict_utf8(self):
  expected=data.normalize('crowdsec','{"sources":2}','jsonb',True)
  self.assertEqual(data.normalize('crowdsec',b'{"sources":2}','jsonb',True),expected)
  self.assertEqual(data.adapted('crowdsec',b'{"sources":2}','jsonb'),'{"sources":2}')
  for value in (b'\xff',b'{"x":"a\x00b"}'):
   with self.assertRaises(ValueError):data.normalize('crowdsec',value,'jsonb',True)
  with self.assertRaises(ValueError):data.normalize('crowdsec',b'{}','jsonb',False)
  with self.assertRaises(ValueError):data.normalize('excalidash',b'{}','jsonb',True)
 def test_native_float4_text_preserves_original_binary32_value(self):
  a=data.normalize('crowdsec',10.199999809265137,'real',True)
  self.assertEqual(a,data.normalize('crowdsec',10.2,'real',False))
 def test_duplicate_rows_and_field_coverage(self):
  columns={'id':'integer','value':'text'};rows=[{'id':1,'value':'a'},{'id':1,'value':'a'}]
  self.assertEqual(len(data.canonical_rows('excalidash',rows,columns,True)),2)
  with self.assertRaises(ValueError):data.canonical_rows('excalidash',[{'id':1}],columns,True)
  self.assertNotEqual(data.canonical_rows('excalidash',rows,columns,True),data.canonical_rows('excalidash',rows[:1],columns,False))
if __name__=='__main__':unittest.main()
