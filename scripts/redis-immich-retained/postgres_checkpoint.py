"""PG17 native logical proof. Files include real records/verifiers: keep private."""
import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path


def compare(expected, actual):
    before, after = copy.deepcopy(expected), copy.deepcopy(actual)
    same_identity = before.pop('physical_system_identifier') == after.pop('physical_system_identifier')
    if before.get('version') != 1 or after.get('version') != 1:
        raise ValueError('Unsupported PostgreSQL checkpoint')
    if set(before['databases']) != set(after['databases']):
        raise ValueError('Database inventory changed')
    for database, proof in before['databases'].items():
        target = after['databases'][database]
        if set(proof['sequences']) != set(target['sequences']):
            raise ValueError('Sequence inventory changed')
        for name, sequence in proof['sequences'].items():
            current = target['sequences'][name]
            old_value, new_value = sequence.pop('last_value'), current.pop('last_value')
            old_called, new_called = sequence.pop('is_called'), current.pop('is_called')
            if sequence != current or type(old_value) is not int or type(new_value) is not int:
                raise ValueError('Sequence definition changed')
            increment = sequence['increment']
            if not increment or (new_value - old_value) * increment < 0 or (old_called and not new_called):
                raise ValueError('Sequence floor decreased')
            if sequence['cycle'] and (new_value != old_value or new_called != old_called):
                raise ValueError('Cyclic sequence state changed')
    if before != after:
        raise ValueError('PostgreSQL records/schema/roles/extensions changed')
    return {'logical_preserved': True, 'physical_identity_equal': same_identity}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _dump_digest(data):
    # Only the unpredictable psql safety token is excluded from the comparison.
    # Original native dump files remain untouched, including their safety token.
    return _sha(b'\n'.join(line for line in data.splitlines()
                           if not line.startswith((b'\\restrict ', b'\\unrestrict '))))


STATE_SQL = r"""
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL timezone='UTC'; SET LOCAL datestyle='ISO, YMD';
SET LOCAL bytea_output='hex'; SET LOCAL extra_float_digits=3;
SELECT 'T|'||encode(convert_to(json_build_array(n.nspname,c.relname)::text,'UTF8'),'hex')
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r','p','m') AND n.nspname NOT IN ('pg_catalog','information_schema')
AND n.nspname NOT LIKE 'pg_toast%' ORDER BY n.nspname,c.relname;
SELECT format($command$COPY (SELECT 'R|'||%L||'|'||encode(convert_to(row_to_json(r)::text,'UTF8'),'hex')
FROM %I.%I r ORDER BY convert_to(row_to_json(r)::text,'UTF8')) TO STDOUT$command$,
encode(convert_to(json_build_array(n.nspname,c.relname)::text,'UTF8'),'hex'),n.nspname,c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r','p','m') AND n.nspname NOT IN ('pg_catalog','information_schema')
AND n.nspname NOT LIKE 'pg_toast%' ORDER BY n.nspname,c.relname
\gexec
SELECT format($command$SELECT 'S|'||%L||'|'||encode(convert_to(json_build_object(
'last_value',last_value,'is_called',is_called,'increment',%s,'cycle',%L::boolean)::text,'UTF8'),'hex') FROM %I.%I$command$,
encode(convert_to(json_build_array(n.nspname,c.relname)::text,'UTF8'),'hex'),s.seqincrement,s.seqcycle,n.nspname,c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_sequence s ON s.seqrelid=c.oid
ORDER BY n.nspname,c.relname
\gexec
COMMIT;
"""


def export(connection_file: Path, destination: Path):
    """Use pinned native CLI tools with quiesced writers; never log their output.

    connection_file is private JSON containing argv_prefix, user and database.
    argv_prefix allows the existing supervised transport to reach native binaries;
    no shell interpolation or plaintext password argument is used here.
    """
    connection_file, destination = Path(connection_file), Path(destination)
    stat = connection_file.lstat()
    if connection_file.is_symlink() or stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        raise ValueError('Private PostgreSQL connection file refused')
    config = json.loads(connection_file.read_text())
    prefix = config.get('argv_prefix', [])
    if not isinstance(prefix, list) or not all(isinstance(value, str) for value in prefix):
        raise ValueError('Invalid native command prefix')
    old_umask = os.umask(0o077)
    try:
        destination.mkdir(mode=0o700)
        def native(binary, arguments, label, sql=None):
            path = destination / label
            with path.open('xb') as output, (destination / (label + '.stderr')).open('xb') as error:
                result = subprocess.run([*prefix, '/usr/bin/' + binary, *arguments],
                    input=None if sql is None else sql.encode('utf8'), stdout=output, stderr=error, timeout=600)
            if result.returncode:
                raise ValueError('Native PostgreSQL proof refused; inspect private diagnostics')
            return path
        def psql(database, sql, label):
            return native('psql', ['-X', '-q', '-A', '-t', '-w', '-U', config['user'], '-d', database,
                                  '-v', 'ON_ERROR_STOP=1'], label, sql)
        bootstrap = config['database']
        identity = json.loads(psql(bootstrap, "SELECT json_build_object('physical_system_identifier',system_identifier::text,'server_version',current_setting('server_version')) FROM pg_control_system();", 'identity.json').read_text())
        if not identity['server_version'].startswith('17.'):
            raise ValueError('Expected PostgreSQL 17')
        inventory = json.loads(psql(bootstrap, "SELECT coalesce(json_agg(r),'[]') FROM (SELECT datname,pg_get_userbyid(datdba) owner,pg_encoding_to_char(encoding) encoding,datcollate,datctype,datistemplate,datallowconn,datconnlimit,datacl::text FROM pg_database ORDER BY datname) r;", 'databases.json').read_text())
        globals_file = native('pg_dumpall', ['-w', '-U', config['user'], '-l', bootstrap, '--globals-only', '--quote-all-identifiers'], 'globals.sql')
        proof = dict(version=1, **identity, globals_sha256=_dump_digest(globals_file.read_bytes()), database_catalog=inventory, databases={})
        for entry in inventory:
            if not entry['datallowconn']:
                continue
            database = entry['datname']
            label = hashlib.sha256(database.encode()).hexdigest()
            foreign = psql(database, 'SELECT count(*) FROM pg_foreign_table;', label + '-foreign.txt').read_text().strip()
            if foreign != '0':
                raise ValueError('External foreign tables require a separate recovery contract')
            schema = native('pg_dump', ['-w', '-U', config['user'], '-d', database, '--schema-only', '--quote-all-identifiers'], label + '-schema.sql')
            # Full independent logical recovery artifact, not a source for CSI.
            native('pg_dump', ['-w', '-U', config['user'], '-d', database, '--format=custom'], label + '.dump')
            rows = psql(database, STATE_SQL, label + '-state.txt')
            tables, sequences, hashes = {}, {}, {}
            with rows.open('rt', encoding='ascii') as lines:
                for line in lines:
                    parts = line.rstrip('\n').split('|')
                    kind = parts[0]
                    if kind not in ('T', 'R', 'S') or len(parts) != (2 if kind == 'T' else 3):
                        raise ValueError('Unexpected native state record')
                    name = json.dumps(json.loads(bytes.fromhex(parts[1])), ensure_ascii=True, separators=(',', ':'))
                    if kind == 'T':
                        if name in tables:
                            raise ValueError('Duplicate native table header')
                        tables[name] = {'rows': 0}
                        hashes[name] = hashlib.sha256()
                    elif kind == 'R':
                        record = bytes.fromhex(parts[2])
                        # Length framing retains duplicate rows and prevents
                        # ambiguous concatenation without storing values in proof.
                        hashes[name].update(len(record).to_bytes(8, 'big') + record)
                        tables[name]['rows'] += 1
                    else:
                        if name in sequences:
                            raise ValueError('Duplicate native sequence')
                        sequences[name] = json.loads(bytes.fromhex(parts[2]))
            for name, table in tables.items():
                table['sha256'] = hashes[name].hexdigest()
            proof['databases'][database] = {'schema_sha256': _dump_digest(schema.read_bytes()), 'tables': tables, 'sequences': sequences}
        (destination / 'checkpoint.json').write_text(json.dumps(proof, sort_keys=True, indent=2) + '\n')
        return proof
    finally:
        os.umask(old_umask)
