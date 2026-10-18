"""Private, binary-safe Redis state. Never print a checkpoint to public logs."""
import base64
import json

TYPES = {'string', 'list', 'set', 'hash', 'zset', 'stream'}


def _validate(checkpoint):
    if checkpoint.get('version') != 1 or type(checkpoint.get('captured_at_ms')) is not int:
        raise ValueError('Invalid checkpoint version/clock')
    for db, records in checkpoint['databases'].items():
        if type(db) is not int or db < 0:
            raise ValueError('Invalid database')
        for key, record in records.items():
            if not isinstance(key, bytes) or record['type'] not in TYPES:
                raise ValueError('Unsupported key/type')
            expiry = record['expires_at_ms']
            if expiry is not None and (type(expiry) is not int or expiry < 0):
                raise ValueError('Invalid absolute expiration')


def compare(expected, actual, now_ms):
    """Compare frozen state; only a known absolute deadline explains absence."""
    _validate(expected)
    _validate(actual)
    if type(now_ms) is not int or now_ms < max(expected['captured_at_ms'], actual['captured_at_ms']):
        raise ValueError('Comparison clock precedes checkpoint')
    preserved = expired = 0
    for db in set(expected['databases']) | set(actual['databases']):
        before = expected['databases'].get(db, {})
        after = actual['databases'].get(db, {})
        if set(after) - set(before):
            raise ValueError('Unexpected key in frozen dataset')
        for key, record in before.items():
            if key not in after:
                if record['expires_at_ms'] is None or record['expires_at_ms'] > actual['captured_at_ms']:
                    raise ValueError('Unexplained missing key')
                expired += 1
            elif after[key] != record:
                raise ValueError('Changed type, payload, metadata or expiry')
            else:
                preserved += 1
    return {'preserved': preserved, 'expired': expired}


def _encode(value):
    if isinstance(value, bytes):
        return ['bytes', base64.b64encode(value).decode('ascii')]
    if isinstance(value, dict):
        return ['dict', [[_encode(k), _encode(v)] for k, v in value.items()]]
    if isinstance(value, (tuple, list)):
        return ['list', [_encode(v) for v in value]]
    if value is None or type(value) in (str, int, float, bool):
        return ['scalar', value]
    raise ValueError('Unsupported checkpoint value')


def _decode(value):
    kind, data = value
    if kind == 'bytes':
        return base64.b64decode(data, validate=True)
    if kind == 'dict':
        pairs = [(_decode(k), _decode(v)) for k, v in data]
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError('Duplicate checkpoint member')
        return result
    if kind == 'list':
        return [_decode(v) for v in data]
    if kind == 'scalar' and (data is None or type(data) in (str, int, float, bool)):
        return data
    raise ValueError('Invalid checkpoint encoding')


def dumps(checkpoint):
    _validate(checkpoint)
    return json.dumps(_encode(checkpoint), ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def loads(text):
    try:
        checkpoint = _decode(json.loads(text))
        _validate(checkpoint)
        return checkpoint
    except (TypeError, KeyError, IndexError, AttributeError) as exc:
        raise ValueError('Invalid checkpoint') from exc


def source_time_ms(client):
    seconds, microseconds = client.time()
    return seconds * 1000 + microseconds // 1000


def _read_database(client):
    records = {}
    for key in set(client.scan_iter(count=1000)):
        # MULTI prevents expiry or another command interleaving the metadata/value
        # reads. The entire frozen capture is checked again below.
        with client.pipeline(transaction=True) as pipe:
            pipe.type(key)
            pipe.pexpiretime(key)
            kind, expiry = pipe.execute()
        if kind == b'none':
            continue
        if kind.decode('ascii') not in TYPES:
            raise ValueError('Unsupported native/module type')
        kind = kind.decode('ascii')
        with client.pipeline(transaction=True) as pipe:
            if kind == 'string':
                pipe.get(key)
            elif kind == 'list':
                pipe.lrange(key, 0, -1)
            elif kind == 'set':
                pipe.smembers(key)
            elif kind == 'hash':
                pipe.hgetall(key)
            elif kind == 'zset':
                # Raw score text avoids a float roundtrip.
                pipe.execute_command('ZRANGE', key, 0, -1, 'WITHSCORES')
            else:
                # FULL COUNT 0 includes native group offsets, pending owners,
                # delivery timestamps/counts and consumer metadata.
                pipe.execute_command('XINFO', 'STREAM', key, 'FULL', 'COUNT', 0)
            pipe.pexpiretime(key)
            value, final_expiry = pipe.execute()
        if final_expiry == -2:
            if expiry < 0 or expiry > source_time_ms(client):
                raise ValueError('Key disappeared without a deadline')
            continue
        if final_expiry != expiry:
            raise ValueError('Source expiry changed while frozen')
        if kind == 'set':
            value = sorted(value)
        elif kind == 'hash':
            fields = sorted(value)
            if fields:
                deadlines = client.execute_command('HPEXPIRETIME', key, 'FIELDS', len(fields), *fields)
                if any(deadline != -1 for deadline in deadlines):
                    raise ValueError('Hash-field expiration requires separate qualification')
            value = [[field, value[field]] for field in fields]
        records[key] = {'type': kind, 'value': value, 'expires_at_ms': None if expiry == -1 else expiry}
    return records


def capture(client, captured_at_ms):
    """Capture quiescent Redis with redis-py 5.2.1 and native absolute clocks.

    Use a single_connection_client so SELECT cannot leak through a connection
    pool. Runtime callers must keep all producers/consumers quiescent.
    """
    if client.connection is None:
        raise ValueError('Use single_connection_client=True for database selection')
    if client.get_encoder().decode_responses:
        raise ValueError('Redis responses must be binary')
    now = source_time_ms(client)
    if not isinstance(captured_at_ms, int) or not 0 <= now - captured_at_ms <= 5000:
        raise ValueError('Source clock/capture boundary is unverified')
    databases = client.config_get('databases')
    count = int(databases.get('databases', databases.get(b'databases', 0)))
    if not 1 <= count <= 1024:
        raise ValueError('Unexpected Redis database count')
    try:
        passes = []
        for _ in range(2):
            state = {'version': 1, 'captured_at_ms': source_time_ms(client), 'databases': {}}
            for index in range(count):
                client.execute_command('SELECT', index)
                state['databases'][index] = _read_database(client)
            passes.append(state)
        compare(passes[0], passes[1], source_time_ms(client))
        return passes[1]
    finally:
        client.execute_command('SELECT', 0)
