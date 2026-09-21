"""Read-only native recovery inspection; no create, delete, format or repair path."""
from identity import verify_native


def read_state(nas):
    return {
        'version': nas.call('system.version'),
        'basename': nas.call('iscsi.global.config')['basename'],
        'pools': nas.call('pool.query'),
        'datasets': nas.call('pool.dataset.query', [['type', '=', 'VOLUME']],
                             {'extra': {'properties': ['guid', 'volsize', 'sync', 'volblocksize']}}),
        'extents': nas.call('iscsi.extent.query'),
        'targets': nas.call('iscsi.target.query'),
        'mappings': nas.call('iscsi.targetextent.query'),
        'portals': nas.call('iscsi.portal.query'),
        'initiators': nas.call('iscsi.initiator.query'),
        'auth': nas.call('iscsi.auth.query', [], {'select': ['tag', 'user']}),
    }


def verify_existing(nas, record):
    state = read_state(nas)
    verify_native(record, state)
    return {'native_verified': True, 'service': record['service']}
