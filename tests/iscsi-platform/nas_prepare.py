"""Prepare only the empty lab data disk, using the pinned private NAS API."""
import json
import time
from nas_rpc import NAS,PRIVATE

nas=NAS()
disks=nas.call('disk.query');boot=nas.call('boot.get_disks')
data=[d for d in disks if d['serial']=='ISCSILABDATA']
assert len(data)==1 and data[0]['name']=='sdb' and data[0]['size']==16*1024**3 and 'sdb' not in boot
pools=nas.call('pool.query');assert not pools, 'Existing data pool requires reconciliation'
job=nas.call('pool.create',{'name':'iscsi_lab','topology':{'data':[{'type':'STRIPE','disks':['sdb']}]}})
while True:
    state=nas.call('core.get_jobs',[['id','=',job]])[0]
    if state['state'] in ('SUCCESS','FAILED','ABORTED'):break
    time.sleep(2)
assert state['state']=='SUCCESS',state.get('error')
pool=nas.call('pool.query',[['name','=','iscsi_lab']])[0]
for suffix in ('volumes','snapshots'):
    nas.call('pool.dataset.create',{'name':'iscsi_lab/'+suffix,'type':'FILESYSTEM'})
record={'id':pool['id'],'name':pool['name'],'guid':pool['guid'],'data_disk_serial':'ISCSILABDATA','boot_disks':boot}
(PRIVATE/'nas-pool.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
