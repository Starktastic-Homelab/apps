"""Cold configuration archives on the approved independent laptop filesystem."""
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import threading
import time
import uuid

BACKUP_ROOT = Path('/home/benf/Backups/homelab/jellyfin')
IMAGE = 'lscr.io/linuxserver/jellyfin:12.1ubu2604-ls50@sha256:51252e7a416e703cdc3cd91e8a54673a2430cc80409be8a38abe511411577b95'
EXCLUSIONS = ['cache', 'data/transcodes']
TAR_OPTIONS = ['--format=pax', '--numeric-owner', '--acls', '--xattrs', '--xattrs-include=*',
               '--exclude=./cache', '--exclude=./data/transcodes']


def inventory(source):
    result = {}
    for path in [source] + sorted(source.rglob('*')):
        relative = path.relative_to(source).as_posix()
        if any(relative == x or relative.startswith(x + '/') for x in EXCLUSIONS):
            continue
        info = path.lstat()
        entry = dict(uid=info.st_uid, gid=info.st_gid, mode=stat.S_IMODE(info.st_mode), mtime_ns=info.st_mtime_ns,
                     xattrs={name: base64.b64encode(os.getxattr(path, name, follow_symlinks=False)).decode()
                             for name in os.listxattr(path, follow_symlinks=False)})
        if path.is_symlink():
            entry.update(type='link', target=os.readlink(path))
        elif path.is_dir():
            entry.update(type='directory')
        elif path.is_file():
            with path.open('rb') as stream:
                entry.update(type='file', sha256=hashlib.file_digest(stream, 'sha256').hexdigest(), bytes=info.st_size)
        else:
            raise ValueError('Special files are not a configuration backup')
        result[relative] = entry
    return result


def write_json(path, value):
    with open(path, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush(); os.fsync(stream.fileno())


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _destination(destination):
    destination = Path(destination).absolute()
    if destination != destination.resolve() or not destination.is_relative_to(BACKUP_ROOT.absolute()) or destination == BACKUP_ROOT:
        raise ValueError('Backup destination must be a new private directory under the approved encrypted home backup root')
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    destination.chmod(0o700)
    return destination


def capture_stream(command, destination, metadata, source_inventory, guard=None):
    if (metadata.get('image') != IMAGE or metadata.get('held') is not True or metadata.get('no_writers') is not True
            or not metadata.get('source', {}).get('dataset_guid') or not metadata.get('snapshot', {}).get('guid')):
        raise ValueError('Exact held-source/image/snapshot evidence required')
    destination = _destination(destination)
    partial = destination/'config.tar.partial'; archive = destination/'config.tar'
    producer = None; watcher = None; stop = threading.Event(); failures = []

    def watch():
        while not stop.wait(1):
            try: guard()
            except Exception:
                failures.append('Source hold or reader identity lost')
                producer.terminate()
                return

    try:
        if guard: guard()
        with open(destination/'producer-private.log', 'xb', opener=lambda p, f: os.open(p, f, 0o600)) as error_log:
            producer = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error_log)
            if guard:
                watcher = threading.Thread(target=watch, daemon=True); watcher.start()
            with open(partial, 'xb', opener=lambda p, f: os.open(p, f, 0o600)) as target:
                shutil.copyfileobj(producer.stdout, target, length=1024*1024)
                target.flush(); os.fsync(target.fileno())
            producer.stdout.close()
            if producer.wait() != 0 or failures:
                raise RuntimeError('Backup producer failed; partial archive is not accepted')
            stop.set()
            if watcher: watcher.join()
            if guard: guard()
        if partial.stat().st_size == 0:
            raise ValueError('Empty archive')
        with partial.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        manifest = dict(metadata, captured_at=datetime.now(timezone.utc).isoformat(), sha256=digest,
                        inventory=source_inventory, exclusions=EXCLUSIONS,
                        bytes_source='held-live-NFS-reader', snapshot_role='additional-recovery-point')
        # Do not claim the stream was read from a mounted snapshot.
        write_json(destination/'config.json.partial', manifest)
        os.rename(partial, archive)
        os.rename(destination/'config.json.partial', archive.with_suffix('.json'))
        _sync(destination)
        return archive
    except Exception:
        stop.set()
        if producer and producer.poll() is None:
            producer.terminate()
            try: producer.wait(timeout=10)
            except subprocess.TimeoutExpired: producer.kill(); producer.wait()
        if producer and producer.stdout: producer.stdout.close()
        if watcher: watcher.join(timeout=65)
        archive.unlink(missing_ok=True)
        # Preserve private partial evidence, never call it an accepted archive.
        raise


def capture(source: Path, destination: Path, metadata: dict) -> Path:
    source = Path(source).resolve()
    return capture_stream(['tar'] + TAR_OPTIONS + ['-C', str(source), '-cf', '-', '.'],
                          destination, metadata, inventory(source))


def _safe_member(member, destination):
    path = PurePosixPath(member.name)
    if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
        raise ValueError('Unsafe archive entry')
    if member.issym() or member.islnk():
        target = PurePosixPath(member.linkname)
        if target.is_absolute() or '..' in target.parts:
            raise ValueError('Unsafe archive link')
    # Per-member validation sees links created by preceding entries. Keep original
    # ownership/modes rather than silently accepting the data filter's stripped metadata.
    try: tarfile.data_filter(member, destination)
    except (tarfile.FilterError, OSError): raise ValueError('Archive escapes restore root') from None
    return member


def verify_restore(archive: Path, scratch: Path) -> dict:
    archive = Path(archive); scratch = Path(scratch).absolute()
    manifest = json.loads(archive.with_suffix('.json').read_text())
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != manifest['sha256']:
            raise ValueError('Archive hash mismatch')
    if scratch != scratch.resolve() or scratch.exists():
        raise ValueError('Restore requires a new directory without symlink components')
    scratch.mkdir(mode=0o700, parents=True)
    try:
        with tarfile.open(archive, 'r:') as tar:
            tar.extractall(scratch, filter=_safe_member, numeric_owner=True)
    except (tarfile.TarError, EOFError, OSError):
        raise ValueError('Archive is truncated or could not preserve metadata') from None
    expected = manifest['inventory']
    actual = inventory(scratch)
    if set(actual) != set(expected):
        raise ValueError('Missing or extra restored configuration/plugin files')
    # Python tarfile preserves standard metadata; restore xattrs/ACLs and exact
    # nanosecond timestamps from the independently captured source inventory.
    for relative, entry in sorted(expected.items(), key=lambda item: item[0].count('/'), reverse=True):
        path = scratch/relative
        for name, value in entry['xattrs'].items():
            os.setxattr(path, name, base64.b64decode(value), follow_symlinks=False)
        os.utime(path, ns=(entry['mtime_ns'], entry['mtime_ns']), follow_symlinks=False)
    if inventory(scratch) != expected:
        raise ValueError('Restored hashes, ownership, modes, links or xattrs differ')
    if not (scratch/'data/data/jellyfin.db').is_file() or not (scratch/'system.xml').is_file():
        raise ValueError('Existing full Jellyfin server configuration required')
    checked = 0
    for db in scratch.rglob('*.db'):
        with db.open('rb') as stream:
            if stream.read(16) != b'SQLite format 3\x00': continue
        with sqlite3.connect(db.resolve().as_uri()+'?mode=rw', uri=True) as connection:
            if connection.execute('pragma integrity_check').fetchall() != [('ok',)]:
                raise ValueError('Restored SQLite integrity failure')
        checked += 1
    if not checked: raise ValueError('No SQLite database verified')
    return {'files_verified': True, 'sqlite_verified': True, 'application_verified': False,
            'archive_sha256': manifest['sha256']}


def verify_application(archive, scratch, api_key_file):
    """Start the exact image on a second restored copy, with no external network."""
    result = verify_restore(archive, scratch)
    manifest = json.loads(Path(archive).with_suffix('.json').read_text())
    required = ('server_id_sha256', 'user_count', 'item_counts', 'plugins')
    if any(k not in manifest for k in required):
        raise ValueError('Private pre-hold application baseline required for restore acceptance')
    key_path = Path(api_key_file)
    if key_path.is_symlink() or key_path.stat().st_mode & 0o077:
        raise ValueError('Restore API key must be a private file')
    key = key_path.read_text().strip()
    if not key or '\n' in key or '"' in key: raise ValueError('Invalid API key file')
    name = 'jellyfin-restore-' + uuid.uuid4().hex
    subprocess.run(['docker', 'image', 'inspect', IMAGE], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['docker', 'run', '-d', '--name', name, '--network', 'none', '--memory', '2g',
                    '--mount', 'type=bind,src='+str(Path(scratch).resolve())+',dst=/config',
                    '-e', 'PUID=1000', '-e', 'PGID=1000', IMAGE], check=True, stdout=subprocess.DEVNULL)
    try:
        def request(path):
            # Key is passed on stdin, not command arguments or logs.
            response = subprocess.run(['docker', 'exec', '-i', name, 'curl', '-fsS', '--max-time', '5',
                                       '--config', '-', 'http://127.0.0.1:8096'+path],
                                      input='header = '+json.dumps('Authorization: MediaBrowser Token="'+key+'"')+'\n', text=True, capture_output=True)
            if response.returncode: raise RuntimeError('Isolated restore API is not ready')
            return response.stdout
        deadline = time.monotonic()+180
        while True:
            try:
                if request('/health').strip() == 'Healthy': break
            except RuntimeError: pass
            if time.monotonic() >= deadline: raise RuntimeError('Restored Jellyfin never became Healthy')
            time.sleep(2)
        public = json.loads(request('/System/Info/Public'))
        if public.get('StartupWizardCompleted') is not True or hashlib.sha256(public['Id'].encode()).hexdigest() != manifest['server_id_sha256']:
            raise ValueError('Restore opened a new or wrong server')
        if len(json.loads(request('/Users'))) != manifest['user_count'] or json.loads(request('/Items/Counts')) != manifest['item_counts']:
            raise ValueError('Restored user/catalog counts differ')
        plugins = [{k: p.get(k) for k in ('Id', 'Version', 'Status')} for p in json.loads(request('/Plugins'))]
        if sorted(plugins, key=lambda p: p['Id']) != sorted(manifest['plugins'], key=lambda p: p['Id']):
            raise ValueError('Plugin loading differs from the pre-hold baseline')
        logs = subprocess.check_output(['docker', 'logs', name], stderr=subprocess.STDOUT).decode(errors='replace')
        if any(token in logs for token in ('LiteException', 'SQLite Error', 'database disk image is malformed')):
            raise ValueError('Restored application reported a database/plugin error')
        result['application_verified'] = True
        write_json(Path(archive).parent/'passed.json', dict(result, verified_at=datetime.now(timezone.utc).isoformat()))
        return result
    finally:
        subprocess.run(['docker', 'rm', '-f', name], check=True, stdout=subprocess.DEVNULL)


def capture_pod(kubeconfig, destination, metadata):
    """Laptop side: only read a reader already created/owned by the runner workflow."""
    import inspect
    ns = metadata['reader']['namespace']; reader = metadata['reader']['name']
    prefix = ['kubectl', '--kubeconfig', str(kubeconfig)]
    def get(*args):
        result = subprocess.run(prefix+list(args)+['-o','json'],check=True,capture_output=True,text=True,timeout=30)
        return json.loads(result.stdout)
    def guard():
        deployment = get('-n',ns,'get','deployment','jellyfin')
        if deployment['spec']['replicas'] != 0 or deployment['spec']['template']['spec']['containers'][0]['image'] != IMAGE:
            raise RuntimeError('Source deployment is not held on the reviewed image')
        application = get('-n','argocd','get','application','jellyfin')
        revisions = application.get('status',{}).get('sync',{}).get('revisions',[])
        revisions.append(application.get('status',{}).get('sync',{}).get('revision',''))
        if metadata['source_held_revision'] not in revisions or application['status']['sync']['status'] != 'Synced':
            raise RuntimeError('Source-held Git revision is not reconciled')
        job = get('-n',ns,'get','cronjob','jellyfin-ldap-library-sync')
        if job['spec'].get('suspend') is not True:
            raise RuntimeError('Jellyfin API writer job is not suspended')
        jobs = get('-n',ns,'get','jobs')['items']
        if any(j.get('status',{}).get('active',0) and any(o.get('name')==job['metadata']['name'] for o in j['metadata'].get('ownerReferences',[])) for j in jobs):
            raise RuntimeError('A Jellyfin API job is still active')
        claim = get('-n',ns,'get','pvc','jellyfin-config')
        pv = get('get','pv',claim['spec']['volumeName'])
        if claim['metadata']['uid'] != metadata['source']['claim_uid'] or pv['spec']['nfs'] != {'server':'10.9.8.30','path':metadata['source']['path']}:
            raise RuntimeError('Source claim/NFS identity changed')
        pods = get('-n',ns,'get','pods')['items']; found=False
        for pod in pods:
            consumes = any(v.get('persistentVolumeClaim',{}).get('claimName') in ('jellyfin-config','jellyfin-config-iscsi') for v in pod['spec'].get('volumes',[]))
            if not consumes:continue
            if pod['metadata']['name'] != reader or pod['metadata']['uid'] != metadata['reader']['uid']:
                raise RuntimeError('Unexpected source or target configuration consumer')
            if not all(v.get('persistentVolumeClaim',{}).get('readOnly') is True for v in pod['spec']['volumes'] if 'persistentVolumeClaim' in v):
                raise RuntimeError('Reader is not read-only')
            found=True
        if not found:raise RuntimeError('Owned reader is missing')
    guard()
    code = ('import os,stat,base64,hashlib,json\nfrom pathlib import Path\nEXCLUSIONS='+repr(EXCLUSIONS)+'\n'
            +inspect.getsource(inventory)+'\nprint(json.dumps(inventory(Path("/config"))))')
    observed = subprocess.run(prefix+['-n',ns,'exec',reader,'--','python3','-c',code],
                              check=True,capture_output=True,text=True)
    guard()
    metadata = dict(metadata, held=True, no_writers=True)
    return capture_stream(prefix+['-n',ns,'exec',reader,'--','tar']+TAR_OPTIONS+['-C','/config','-cf','-','.'],
                          destination,metadata,json.loads(observed.stdout),guard=guard)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='operation',required=True)
    capture_parser=sub.add_parser('capture-pod')
    capture_parser.add_argument('--kubeconfig',type=Path,required=True)
    capture_parser.add_argument('--metadata',type=Path,required=True)
    capture_parser.add_argument('--destination',type=Path,required=True)
    for name in ('verify-files','verify-application'):
        p=sub.add_parser(name);p.add_argument('--archive',type=Path,required=True);p.add_argument('--scratch',type=Path,required=True)
        if name=='verify-application':p.add_argument('--api-key-file',type=Path,required=True)
    args=parser.parse_args()
    if args.operation=='capture-pod':
        result={'archive':str(capture_pod(args.kubeconfig,args.destination,json.loads(args.metadata.read_text())))}
    elif args.operation=='verify-files':result=verify_restore(args.archive,args.scratch)
    else:result=verify_application(args.archive,args.scratch,args.api_key_file)
    print(json.dumps(result))


if __name__=='__main__':main()
