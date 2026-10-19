#!/usr/bin/env python3
"""Rehearse the pinned stock CWA split layout using only isolated synthetic state."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    pin = yaml.safe_load((ROOT / 'services/media/calibre-web/values.yaml').read_text())['controllers']['main']['containers']['main']['image']
    image = pin['repository'] + ':' + pin['tag']
    uid, gid = os.getuid(), os.getgid()
    token = uuid.uuid4().hex
    names = ['cwa-native-' + token[:12], 'cwa-native-' + token[:12] + '-recovered']

    def docker(args, timeout=120):
        result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError('Synthetic CWA command failed: ' + result.stderr[-2200:])
        return result.stdout

    root = Path(tempfile.mkdtemp(prefix='cwa-native-'))
    try:
        (root / '.fixture-owner').write_text(token)
        source, target, books, ingest = (root / p for p in ('source', 'target', 'books', 'ingest'))
        for p in (source, target, books, ingest, source / 'config', source / 'library'):
            p.mkdir()

        def mounts(state):
            result = []
            for p, dest in ((state / 'config', '/config'), (state / 'library', '/calibre-library'),
                            (books, '/calibre-books'), (ingest, '/cwa-book-ingest')):
                result += ['--mount', 'type=bind,src=' + str(p) + ',dst=' + dest]
            return result

        def native(code, state=source, calibre=False, user=True):
            args = ['run', '--rm', '--network', 'none', '--label', 'homelab-synthetic=' + token, *mounts(state), '-e', 'CALIBRE_CONFIG_DIRECTORY=/tmp/calibre',
                    '-e', 'CALIBRE_OVERRIDE_DATABASE_PATH=/calibre-library/metadata.db']
            if user:
                args += ['--user', str(uid) + ':' + str(gid)]
            command = '/app/calibre/calibre-debug' if calibre else 'python3'
            args += ['--entrypoint', command, image, *(['-c'] if calibre else ['-I', '-B', '-c']),
                     "exec(compile(" + repr(code) + ", 'synthetic-native', 'exec', optimize=0), {'__name__':'__main__'})"]
            return docker(args)

        def launch(state, name):
            cid = docker(['run', '--detach', '--network', 'none', '--name', name,
                          '--label', 'homelab-synthetic=' + token, *mounts(state),
                          '-e', 'NETWORK_SHARE_MODE=true', '-e', 'PUID=' + str(uid), '-e', 'PGID=' + str(gid), image]).strip()
            return cid

        def ready(cid):
            docker(['exec', cid, 'python3', '-I', '-B', '-c', r'''
import urllib.request,time
end=time.monotonic()+60
while True:
 try:
  assert urllib.request.urlopen('http://127.0.0.1:8083/login',timeout=2).status==200;break
 except Exception:
  if time.monotonic()>end:raise
  time.sleep(1)
'''], 75)

        try:
            native(r'''
from calibre.db.legacy import LibraryDatabase
from calibre.ebooks.metadata.book.base import Metadata
db=LibraryDatabase('/calibre-books');api=db.new_api
book=api.create_book_entry(Metadata('Synthetic retained book',['Synthetic Author']));assert book==1
api.set_notes_for('authors',api.get_item_id('authors','Synthetic Author'),'<p>Retained author note</p>');db.close()
''', calibre=True)
            first = launch(source, names[0]); ready(first)
            docker(['stop', '--timeout', '30', first])
            native(r'''
import sqlite3
with sqlite3.connect('/config/app.db')as c:
 c.execute("UPDATE settings SET config_calibre_dir='/calibre-library',config_calibre_split=1,config_calibre_split_dir='/calibre-books'")
''')
            docker(['start', first]); ready(first)
            docker(['exec', '--user', str(uid) + ':' + str(gid), '-e', 'CALIBRE_OVERRIDE_DATABASE_PATH=/calibre-library/metadata.db',
                    '-e', 'CALIBRE_CONFIG_DIRECTORY=/tmp/calibre', first, '/app/calibre/calibre-debug', '-c', r'''
from pathlib import Path
from calibre.db.legacy import LibraryDatabase
import subprocess,shutil,io
from PIL import Image
p=Path('/tmp/fixture.txt');p.write_text('Synthetic retained library content.\n'*40)
subprocess.run(['/app/calibre/ebook-convert',str(p),'/tmp/fixture.epub','--title','Synthetic retained book','--authors','Synthetic Author'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=60)
db=LibraryDatabase('/calibre-books');api=db.new_api
with open('/tmp/fixture.epub','rb')as f:api.add_format(1,'EPUB',f)
buf=io.BytesIO();Image.new('RGB',(32,48),(80,110,180)).save(buf,format='JPEG');api.set_cover({1:buf.getvalue()});db.close()
subprocess.run(['/app/calibre/ebook-convert',str(p),'/tmp/import.azw3','--title','Synthetic conversion import','--authors','Different Author'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=60)
shutil.copyfile('/tmp/import.azw3','/cwa-book-ingest/.fixture.partial');Path('/cwa-book-ingest/.fixture.partial').rename('/cwa-book-ingest/Synthetic conversion import.azw3')
'''])
            docker(['exec', first, 'python3', '-I', '-B', '-c', r'''
import sqlite3,time
end=time.monotonic()+90
while True:
 with sqlite3.connect('/calibre-library/metadata.db')as c:n=c.execute('SELECT count(*) FROM books').fetchone()[0]
 with sqlite3.connect('/config/cwa.db')as c:converted=c.execute('SELECT count(*) FROM cwa_conversions').fetchone()[0]
 if n==2 and converted==1:break
 assert time.monotonic()<end,'Stock ingest/conversion did not finish';time.sleep(1)
'''], 105)
            web = r'''
import urllib.request,urllib.error,urllib.parse,http.cookiejar,re,sqlite3,json,zipfile,io,hashlib,time
from pathlib import Path
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));base='http://127.0.0.1:8083'
page=op.open(base+'/login').read().decode();csrf=re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
end=time.monotonic()+30
while True:
 try:
  html=op.open(urllib.request.Request(base+'/login',data=urllib.parse.urlencode({'username':'admin','password':'admin123','csrf_token':csrf,'next':'/'}).encode())).read().decode();assert'/logout'in html;break
 except urllib.error.HTTPError as e:
  if e.code!=500 or time.monotonic()>end:raise
  # Stock ingest reopens its web database after the conversion completes.
  time.sleep(1)
if EDIT:
 page=op.open(base+'/admin/book/1').read().decode();csrf=re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
 fields={'csrf_token':csrf,'title':'Synthetic web edited book','authors':'Synthetic Author','tags':'migration','series':'','series_index':'1','pubdate':'','publisher':'','languages':'English','rating':'','cover_url':'','detail_view':'on','description':'Stock split web edit'}
 op.open(urllib.request.Request(base+'/admin/book/1',data=urllib.parse.urlencode(fields).encode()),timeout=30).read()
with sqlite3.connect('/calibre-library/metadata.db')as c:
 row=c.execute('SELECT title,path FROM books WHERE id=1').fetchone();assert row[0]=='Synthetic web edited book'
 path=c.execute("SELECT books.path||'/'||data.name||'.epub' FROM books JOIN data ON data.book=books.id WHERE books.id=1 AND data.format='EPUB'").fetchone()[0]
assert(Path('/calibre-books')/row[1]).is_dir()and not(Path('/calibre-library')/row[1]).exists()
assert row[0]in op.open(base+'/book/1').read().decode();assert op.open(base+'/cover/1').read()[:2]==b'\xff\xd8'
body=op.open(base+'/download/1/epub').read();download=zipfile.ZipFile(io.BytesIO(body));original=zipfile.ZipFile(Path('/calibre-books')/path)
assert download.testzip()is None
texts=[n for n in original.namelist()if n.endswith(('.xhtml','.html'))];assert texts and all(original.read(n)==download.read(n)for n in texts)
assert any(row[0].encode()in download.read(n)for n in download.namelist()if n.endswith('.opf'))
with sqlite3.connect('/calibre-library/metadata.db')as c:
 imported=c.execute("SELECT id,title,path FROM books WHERE title='Synthetic conversion import'").fetchone();assert imported
 formats=list(c.execute('SELECT format,name FROM data WHERE book=?',(imported[0],)));assert any(fmt=='EPUB'for fmt,name in formats),formats
for fmt,name in formats:
 asset=Path(imported[2])/(name+'.'+fmt.lower())
 assert (Path('/calibre-books')/asset).is_file()and not(Path('/calibre-library')/asset).exists(),str(asset)
 body=op.open(base+'/download/'+str(imported[0])+'/'+fmt.lower()).read();assert body
 if fmt=='EPUB':
  archive=zipfile.ZipFile(io.BytesIO(body));assert archive.testzip()is None
  assert any(b'Synthetic retained library content' in archive.read(n)for n in archive.namelist()if n.endswith(('.html','.xhtml')))
paths=[]
for root in('/config','/calibre-library','/calibre-books','/cwa-book-ingest'):
 for p in Path(root).rglob('*'):
  if p.is_file():
   with p.open('rb')as f:header=f.read(16)
   if header==b'SQLite format 3\x00':paths.append(str(p))
assert sorted(paths)==sorted(['/config/app.db','/config/gdrive.db','/config/cwa.db','/calibre-library/metadata.db','/calibre-library/.calnotes/notes.db']),paths
print(json.dumps({'stockLoginEditCoverDownload':True,'allFiveSQLiteOutsideBooksAndIngest':True,'convertedBookOnNfsAndDownloadable':True}))
'''
            initial = json.loads(docker(['exec', first, 'python3', '-I', '-B', '-c', 'EDIT=True\n' + web]))
            docker(['stop', '--timeout', '30', first])
            (source / '.homelab-calibre-web-data').write_text('homelab/calibre-web/data/v1\n')
            cold = r'''
if not __debug__: raise RuntimeError("Native qualification assertions are disabled")
import importlib.util,json,apsw,hashlib
from pathlib import Path
from calibre.constants import plugins
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
copier=load('copier','/tool/copy_files.py');guard=load('guard','/tool/guard.py');source=Path('/fixture/source');target=Path('/fixture/target');guard.validate(source)
def proof(root):
 out={}
 for rel in guard.DATABASES:
  with apsw.Connection(str(root/rel),flags=apsw.SQLITE_OPEN_READONLY)as c:
   plugins.load_apsw_extension(c,'sqlite_extension');assert list(c.execute('PRAGMA integrity_check'))==[('ok',)]
   rows={}
   for(name,)in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    values=list(c.execute('SELECT * FROM "'+name.replace('"','""')+'"'));rows[name]=sorted(json.dumps([{'bytes':v.hex()}if isinstance(v,bytes)else v for v in row],sort_keys=True)for row in values)
   out[rel]=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
 return out
before=proof(source);files=copier.inventory(source);receipt=copier.copy_files(source,target,'.homelab-calibre-web-data','homelab/calibre-web/data/v1\n');guard.validate(target)
assert proof(target)==before and copier.inventory(source)==files and copier.inventory(target)==files
print(json.dumps({'copy':receipt,'allFiveNativeIntegrityAndRowsEqual':True}))
'''
            cold_result = json.loads(docker(['run', '--rm', '--network', 'none', '--label', 'homelab-synthetic=' + token, '--mount', 'type=bind,src=' + str(root) + ',dst=/fixture',
                '--mount', 'type=bind,src=' + str(ROOT / 'scripts/ordinary-file-storage/copy_files.py') + ',dst=/tool/copy_files.py,readonly',
                '--mount', 'type=bind,src=' + str(Path(__file__).with_name('guard.py')) + ',dst=/tool/guard.py,readonly',
                '-e', 'CALIBRE_CONFIG_DIRECTORY=/tmp/calibre', '--entrypoint', '/app/calibre/calibre-debug', image, '-c',
                "exec(compile(" + repr(cold) + ", 'synthetic-cold', 'exec', optimize=0), {'__name__':'__main__'})"]))
            recovered = launch(target, names[1]); ready(recovered)
            final = json.loads(docker(['exec', recovered, 'python3', '-I', '-B', '-c', 'EDIT=False\n' + web]))
            print(json.dumps({'image': image, 'initial': initial, 'coldRecovery': cold_result, 'recoveredStockWeb': final,
                              'nativeConversionAndIngest': True, 'noNetworkOrProductionData': True}))
        finally:
            # Discover ambiguous run outcomes too: Docker may have created a
            # container even when its client timed out before returning the ID.
            for name in names:
                result = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True, timeout=30)
                if result.returncode:
                    if 'no such object' in result.stderr.lower() or 'no such container' in result.stderr.lower():
                        continue
                    raise RuntimeError('Cannot verify synthetic container cleanup')
                info = json.loads(result.stdout)[0]
                if info['Config']['Labels'].get('homelab-synthetic') != token:
                    raise RuntimeError('Named container ownership changed; preserve fixture')
            owned = docker(['ps', '-a', '--no-trunc', '--filter', 'label=homelab-synthetic=' + token, '--format', '{{.ID}}']).splitlines()
            for cid in owned:
                info = json.loads(docker(['inspect', cid]))[0]
                if info['Id'] != cid or info['Config']['Labels'].get('homelab-synthetic') != token:
                    raise RuntimeError('Container ownership changed; preserve fixture')
                docker(['rm', '--force', cid])
            if docker(['ps', '-a', '--filter', 'label=homelab-synthetic=' + token, '--format', '{{.ID}}']).strip():
                raise RuntimeError('Synthetic container remains; preserve fixture')
            # Stock init creates some root-owned fixture files. Clean only this owned root.
            cleanup = "from pathlib import Path;import shutil;r=Path('/fixture');assert(r/'.fixture-owner').read_text()==" + repr(token) + ";\nfor p in r.iterdir():\n if p.is_dir()and not p.is_symlink():shutil.rmtree(p)\n else:p.unlink()"
            docker(['run', '--rm', '--network', 'none', '--label', 'homelab-synthetic=' + token, '--mount', 'type=bind,src=' + str(root) + ',dst=/fixture',
                    '--entrypoint', 'python3', image, '-I', '-B', '-c', cleanup])
            root.rmdir()
    except BaseException:
        # Explicit lifetime: uncertain container cleanup must preserve bind files.
        raise


if __name__ == '__main__':
    main()
