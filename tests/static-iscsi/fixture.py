"""Synthetic SQLite fixture: normal startup cannot create a database."""
import hashlib
import json
import os
import pathlib
import sqlite3
import signal
import sys
import time
from lifecycle import verify_database

path = pathlib.Path('/data/catalog.sqlite')
marker = os.environ['SERVICE_MARKER']
mode = sys.argv[1]
if mode == 'initialize':
    if path.exists() or any(p.name != 'lost+found' for p in path.parent.iterdir()):
        raise SystemExit('Initialization requires verified empty storage')
    connection = sqlite3.connect(path)
    connection.execute('pragma journal_mode=WAL')
    connection.execute('pragma synchronous=FULL')
    connection.execute('create table identity(marker text not null)')
    connection.execute('insert into identity values(?)', (marker,))
    connection.execute('create table transactions(id text primary key, value text not null)')
    connection.commit()
    connection.close()
else:
    verify_database(path, marker)
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True, timeout=20)
    connection.execute('pragma synchronous=FULL')
    if mode == 'write':
        tx = sys.argv[2]
        value = hashlib.sha256((marker + ':' + tx).encode()).hexdigest()
        connection.execute('insert or ignore into transactions values(?,?)', (tx, value))
        connection.commit()
        assert connection.execute('select value from transactions where id=?', (tx,)).fetchone() == (value,)
        print(json.dumps({'marker': marker, 'id': tx, 'value': value}), flush=True)
    elif mode == 'verify':
        rows = connection.execute('select id,value from transactions order by id').fetchall()
        assert all(v == hashlib.sha256((marker+':'+k).encode()).hexdigest() for k,v in rows)
        print(json.dumps({'marker': marker, 'integrity': 'ok', 'rows': rows}))
    elif mode == 'backup':
        with sqlite3.connect('/tmp/backup.sqlite') as backup:
            connection.backup(backup)
        print('Backup complete')
    elif mode == 'serve':
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        print('Verified existing catalog', flush=True)
        connection.close()
        while True:
            time.sleep(30)
    else:
        raise SystemExit('Unknown operation')
