"""Render static resources only from a completed, externally verified identity record."""
import hashlib
import json
import uuid

DRIVER = 'org.democratic-csi.retained'
STAMP = 'storage.starktastic.net/namespace-uid'
WRITER = 'storage.starktastic.net/writer'


def record_hash(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def placement(node):
    expressions = [{'key': key, 'operator': 'In', 'values': [node[field]]} for key, field in (
        ('kubernetes.io/hostname', 'hostname'), ('storage.starktastic.net/generation', 'smbios_uuid'),
        ('storage.starktastic.net/node-uid', 'node_uid'))]
    return {'nodeAffinity': {'requiredDuringSchedulingIgnoredDuringExecution': {'nodeSelectorTerms': [{'matchExpressions': expressions}]}}}


def _policy(name, resource, match, expressions, *, parameter=None):
    metadata = {'name': name, 'annotations': {'argocd.argoproj.io/sync-wave': '-5'}}
    spec = {'failurePolicy': 'Fail', 'matchConstraints': {'resourceRules': [dict(apiGroups=[''], apiVersions=['v1'],
            operations=['CREATE', 'UPDATE'], resources=[resource])]},
            'matchConditions': [{'name': 'retained-scope', 'expression': match}],
            'validations': [{'expression': e, 'message': 'Retained storage identity or writer authorization does not match.'} for e in expressions]}
    binding = {'policyName': name, 'validationActions': ['Deny']}
    if parameter:
        spec['paramKind'] = {'apiVersion': 'v1', 'kind': 'ConfigMap'}
        binding['paramRef'] = dict(name=parameter['name'], namespace=parameter['namespace'], parameterNotFoundAction='Deny')
    return [dict(apiVersion='admissionregistration.k8s.io/v1', kind='ValidatingAdmissionPolicy', metadata=metadata, spec=spec),
            dict(apiVersion='admissionregistration.k8s.io/v1', kind='ValidatingAdmissionPolicyBinding', metadata=metadata, spec=binding)]


def render(record):
    required = ['service', 'marker', 'pool_guid', 'zvol_guid', 'bytes', 'extent_id', 'serial', 'naa', 'target_id',
                'iqn', 'portal', 'lun', 'group', 'initiators', 'auth_networks', 'filesystem_uuid', 'pv', 'pvc', 'namespace']
    if any(k not in record or record[k] is None for k in required):
        raise ValueError('Incomplete native/filesystem record; allocation intent cannot render bindings')
    for key in ('marker', 'filesystem_uuid'):
        try:
            uuid.UUID(record[key])
        except (ValueError, AttributeError):
            raise ValueError('Invalid native service marker or filesystem UUID') from None
    q = json.dumps
    ns, pvcname, pvname = (record[k] for k in ('namespace', 'pvc', 'pv'))
    attributes = dict(node_attach_driver='iscsi', provisioner_driver='node-manual', portal=record['portal'], iqn=record['iqn'], lun=str(record['lun']))
    csi = dict(driver=DRIVER, volumeHandle=record['marker'], fsType='ext4', volumeAttributes=attributes,
               nodeStageSecretRef=dict(name='retained-jellyfin-chap', namespace='retained-iscsi'))
    annotations = {'argocd.argoproj.io/sync-options': 'Prune=false,Delete=false', 'argocd.argoproj.io/sync-wave': '-1'}
    pv = dict(apiVersion='v1', kind='PersistentVolume', metadata=dict(name=pvname, annotations=annotations),
              spec=dict(capacity={'storage': str(record['bytes'])}, accessModes=['ReadWriteOncePod'],
                        persistentVolumeReclaimPolicy='Retain', storageClassName='', volumeMode='Filesystem',
                        claimRef=dict(namespace=ns, name=pvcname), csi=csi))
    pvc = dict(apiVersion='v1', kind='PersistentVolumeClaim', metadata=dict(name=pvcname, namespace=ns, annotations=annotations),
               spec=dict(storageClassName='', volumeName=pvname, accessModes=['ReadWriteOncePod'],
                         resources={'requests': {'storage': str(record['bytes'])}}, volumeMode='Filesystem'))
    items = [pv, pvc]
    alias = f"(has(object.spec.csi) && (object.spec.csi.driver == {q(DRIVER)} || (has(object.spec.csi.volumeAttributes) && 'iqn' in object.spec.csi.volumeAttributes && object.spec.csi.volumeAttributes.iqn == {q(record['iqn'])})))"
    match = f"object.metadata.name == {q(pvname)} || {alias} || (has(object.spec.iscsi) && object.spec.iscsi.iqn == {q(record['iqn'])})"
    items += _policy('retained-jellyfin-volumes', 'persistentvolumes', match, [
        f"object.metadata.name == {q(pvname)} && has(object.spec.csi) && object.spec.csi.driver == {q(DRIVER)} && object.spec.csi.volumeHandle == {q(record['marker'])} && object.spec.csi.fsType == 'ext4' && object.spec.csi.volumeAttributes == {q(attributes)} && object.spec.csi.nodeStageSecretRef.name == 'retained-jellyfin-chap' && object.spec.csi.nodeStageSecretRef.namespace == 'retained-iscsi' && (!has(object.spec.csi.readOnly) || !object.spec.csi.readOnly) && !has(object.spec.csi.nodePublishSecretRef) && !has(object.spec.csi.controllerPublishSecretRef) && object.spec.persistentVolumeReclaimPolicy == 'Retain' && (!has(object.spec.storageClassName) || object.spec.storageClassName == '') && object.spec.accessModes == ['ReadWriteOncePod'] && object.spec.claimRef.name == {q(pvcname)} && object.spec.claimRef.namespace == {q(ns)} && object.spec.volumeMode == 'Filesystem'"])
    items += _policy('retained-jellyfin-claims', 'persistentvolumeclaims',
        f"(object.metadata.namespace == {q(ns)} && object.metadata.name == {q(pvcname)}) || (has(object.spec.volumeName) && object.spec.volumeName == {q(pvname)})", [
        f"object.metadata.namespace == {q(ns)} && object.metadata.name == {q(pvcname)} && has(object.spec.volumeName) && object.spec.volumeName == {q(pvname)} && object.spec.storageClassName == '' && object.spec.accessModes == ['ReadWriteOncePod'] && object.spec.volumeMode == 'Filesystem'"])
    auth = dict(name='retained-jellyfin-authorization', namespace=ns)
    match = f"object.metadata.namespace == {q(ns)} && has(object.spec.volumes) && object.spec.volumes.exists(v, has(v.persistentVolumeClaim) && v.persistentVolumeClaim.claimName == {q(pvcname)})"
    terms = 'object.spec.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms'
    checks = [
        f"has(object.metadata.labels) && {q(WRITER)} in object.metadata.labels && object.metadata.labels[{q(WRITER)}] == 'jellyfin'",
        f"has(params.data) && params.data.released == 'true' && params.data.recordHash == {q(record_hash(record))}",
        f"has(namespaceObject.metadata.annotations) && {q(STAMP)} in namespaceObject.metadata.annotations && params.data.namespaceUID == namespaceObject.metadata.annotations[{q(STAMP)}]",
        "(!has(object.spec.nodeName) || object.spec.nodeName == '') || (request.operation == 'UPDATE' && object.spec.nodeName == params.data.hostname)",
        "has(object.spec.affinity) && has(object.spec.affinity.nodeAffinity) && has(object.spec.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution)",
        f"{terms}.size() == 1 && !has({terms}[0].matchFields) && {terms}[0].matchExpressions.size() == 3",
    ]
    for key, field in [('kubernetes.io/hostname', 'hostname'), ('storage.starktastic.net/generation', 'smbiosUUID'), ('storage.starktastic.net/node-uid', 'nodeUID')]:
        checks.append(f"{terms}[0].matchExpressions.exists(e, e.key == {q(key)} && e.operator == 'In' && e.values == [params.data.{field}])")
    items += _policy('retained-jellyfin-labels', 'pods', match, [checks[0]])
    writer_rules = _policy('retained-jellyfin-writers', 'pods', match, checks, parameter=auth)
    # Missing params are evaluated before matchConditions. Scope the binding by
    # label; the independent parameter-free policy prevents unlabelled bypass.
    writer_rules[1]['spec']['matchResources'] = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': ns}},
                                               'objectSelector': {'matchLabels': {WRITER: 'jellyfin'}}}
    items += writer_rules
    # CEL deliberately hides metadata.uid. Only the external verifier stamps the
    # live API UID, and namespace creation cannot replay a previous stamp.
    items += _policy('retained-namespace-generation', 'namespaces', f"object.metadata.name == {q(ns)}", [
        f"request.operation != 'CREATE' || !has(object.metadata.annotations) || !({q(STAMP)} in object.metadata.annotations)",
        f"request.operation != 'UPDATE' || !has(object.metadata.annotations) || !({q(STAMP)} in object.metadata.annotations) || (has(oldObject.metadata.annotations) && {q(STAMP)} in oldObject.metadata.annotations && object.metadata.annotations[{q(STAMP)}] == oldObject.metadata.annotations[{q(STAMP)}]) || request.userInfo.groups.exists(g, g == 'system:masters') || request.userInfo.username == 'system:serviceaccount:retained-iscsi:storage-maintenance'"])
    # Direct binding bypasses scheduling/affinity. Ordinary media scheduling is
    # unaffected; only the scheduler may bind a pod in this namespace.
    items += _policy('retained-scheduler-binding', 'pods/binding', f"request.namespace == {q(ns)}", [
        "request.userInfo.username == 'system:kube-scheduler'"])
    return items
