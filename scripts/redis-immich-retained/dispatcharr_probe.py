"""Exact-image RedisClient probe; synthetic settings and data only."""
import ast
import hashlib
import json
import logging
import os
import time
from pathlib import Path
import redis
from django.conf import settings

assert redis.__version__ == '6.4.0'
settings.configure(REDIS_HOST='127.0.0.1', REDIS_PORT=6379, REDIS_DB=4,
                   REDIS_PASSWORD='synthetic-fixture-only', REDIS_IDLE_TIMEOUT=300)
os.environ.update(REDIS_HOST='127.0.0.1', REDIS_PORT='6379', REDIS_DB='4',
                  REDIS_PASSWORD='synthetic-fixture-only')
logger = logging.getLogger('synthetic-fixture')
# The service bootstrap adds TRACE; initialize that logging level only.
logger.trace = lambda *args, **kwargs: logger.log(5, *args, **kwargs)
source = Path('/app/core/utils.py').read_text()
assert hashlib.sha256(source.encode()).hexdigest() == 'f39389cae183f8767b48abed38f3d8cc88b6db8e2313b6368d38bae7883ebc08'
node = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'RedisClient')
exec(compile(ast.Module(body=[node], type_ignores=[]), '/app/core/utils.py', 'exec'))
for decode in (True, False):
    client = RedisClient._init_client(decode_responses=decode, max_retries=1)
    assert client is not None and client.ping()
    key = 'synthetic-dispatcharr-' + str(decode)
    client.rpush(key, 'synthetic-payload')
    assert client.lpop(key) == ('synthetic-payload' if decode else b'synthetic-payload')
    client.close()
print(json.dumps({'decoded_and_binary_clients_work': True}))
