"""Generate native admission rules from the captured lab mappings."""
import json
from lab import ROOT, apply
records=json.loads((ROOT/'records.json').read_text())
q=json.dumps
claims=[];volumes=[]
for r in records:
 name=r['service'];p=r['pv'];s=p['spec'];c=s['csi'];a=c['volumeAttributes']
 claims.append(f"(object.metadata.namespace == 'iscsi-fixture' && object.metadata.name == {q(name)} && object.spec.storageClassName == 'iscsi-lab-retain' && object.spec.volumeName == {q(p['metadata']['name'])} && object.spec.accessModes == ['ReadWriteOncePod'])")
 volumes.append(f"(object.metadata.name == {q(p['metadata']['name'])} && object.spec.csi.driver == {q(c['driver'])} && object.spec.csi.volumeHandle == {q(c['volumeHandle'])} && object.spec.csi.fsType == 'ext4' && object.spec.csi.volumeAttributes == {q(a)} && object.spec.csi.nodeStageSecretRef.name == 'iscsi-lab-chap' && object.spec.csi.nodeStageSecretRef.namespace == 'iscsi-lab-system' && object.spec.persistentVolumeReclaimPolicy == 'Retain' && object.spec.storageClassName == 'iscsi-lab-retain' && object.spec.accessModes == ['ReadWriteOncePod'] && object.spec.claimRef.name == {q(name)} && object.spec.claimRef.namespace == 'iscsi-fixture')")
items=[]
for suffix,resource,match,expression in [
 ('claims','persistentvolumeclaims',"(has(object.spec.storageClassName) && object.spec.storageClassName == 'iscsi-lab-retain') || (object.metadata.namespace == 'iscsi-fixture' && object.metadata.name in ['service-a','service-b'])",' || '.join(claims)),
 ('volumes','persistentvolumes',"(has(object.spec.csi) && object.spec.csi.driver == 'org.democratic-csi.iscsi-lab') || object.metadata.name in "+q([r['pv']['metadata']['name'] for r in records]),' || '.join(volumes))]:
 name='iscsi-lab-'+suffix
 items.append({'apiVersion':'admissionregistration.k8s.io/v1','kind':'ValidatingAdmissionPolicy','metadata':{'name':name},'spec':{'failurePolicy':'Fail','matchConstraints':{'resourceRules':[{'apiGroups':[''],'apiVersions':['v1'],'operations':['CREATE','UPDATE'],'resources':[resource]}]},'matchConditions':[{'name':'retained-storage','expression':match}],'validations':[{'expression':expression,'message':'Retained storage must match the captured service binding; dynamic onboarding is closed.'}]}})
 items.append({'apiVersion':'admissionregistration.k8s.io/v1','kind':'ValidatingAdmissionPolicyBinding','metadata':{'name':name},'spec':{'policyName':name,'validationActions':['Deny']}})
(ROOT/'admission.json').write_text(json.dumps({'apiVersion':'v1','kind':'List','items':items},indent=2))
print(apply(items).stdout)
