#!/usr/bin/env python3
"""Exact-image synthetic native index/schedule cold-copy and reopen check."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    image = yaml.safe_load((ROOT / 'services/operations/paperless-ngx/values.yaml').read_text())['controllers']['main']['containers']['main']['image']
    image = image['repository'] + ':' + image['tag']
    copier = load('cold_copy', ROOT / 'scripts/ordinary-file-storage/copy_files.py')
    guard = load('paperless_guard', Path(__file__).with_name('guard.py'))
    with tempfile.TemporaryDirectory(prefix='paperless-native-') as name:
        root = Path(name)
        source, target = root / 'source', root / 'target'
        source.mkdir()
        target.mkdir()

        def native(code, readonly=False):
            mount = 'type=bind,src=' + str(root) + ',dst=/work' + (',readonly' if readonly else '')
            result = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
                                     '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                                     '--user', str(os.getuid()) + ':' + str(os.getgid()),
                                     '--mount', mount, '--entrypoint', 'python3', image,
                                     '-I', '-B', '-c', code], capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise RuntimeError('Native synthetic test failed: ' + result.stderr[-3000:])
            return json.loads(result.stdout)

        create = r'''
from pathlib import Path
import importlib.util,json,dbm.gnu,pickle,tantivy
from django.conf import settings
settings.configure(SEARCH_LANGUAGE='en')
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
base=Path('/usr/src/paperless/src/documents/search');schema=load('native_schema',base/'_schema.py');tokens=load('native_tokens',base/'_tokenizer.py')
root=Path('/work/source');path=root/'index';path.mkdir()
index=tantivy.Index(schema.build_schema(),path=str(path));tokens.register_tokenizers(index,'en');writer=index.writer()
doc=tantivy.Document();doc.add_unsigned('id',7);doc.add_text('title','Synthetic retained record');doc.add_text('content','native recovery fixture');writer.add_document(doc);writer.commit();writer.wait_merging_threads();del writer
schema._write_sentinels(path);(root/'.index_version').write_text('9\n');(root/'.homelab-paperless-data').write_text('homelab/paperless/data/v1\n')
with dbm.gnu.open(str(root/'celerybeat-schedule.db'),'c') as schedule:
 schedule[b'entries']=pickle.dumps({});schedule[b'__version__']=b'synthetic'
print(json.dumps({'nativeIndexCreated':True,'documentID':7}))
'''
        native(create)
        guard.validate(source)
        receipt = copier.copy_files(source, target, '.homelab-paperless-data', 'homelab/paperless/data/v1\n')
        before = copier.inventory(target)
        guard.validate(target)
        reopen = r'''
from pathlib import Path
import importlib.util,json,dbm.gnu,tantivy
spec=importlib.util.spec_from_file_location('tokens','/usr/src/paperless/src/documents/search/_tokenizer.py');tokens=importlib.util.module_from_spec(spec);spec.loader.exec_module(tokens)
r=Path('/work/target');index=tantivy.Index.open(str(r/'index'));tokens.register_tokenizers(index,'en');s=index.searcher();result=s.search(index.parse_query('recovery',['content']),limit=10)
ids=sorted(s.doc(address)['id'][0] for _,address in result.hits);assert ids==[7]
with dbm.gnu.open(str(r/'celerybeat-schedule.db'),'r')as schedule:assert sorted(schedule.keys())==[b'__version__',b'entries']
print(json.dumps({'nativeQueryIDs':ids,'nativeScheduleReadable':True}))
'''
        # Tantivy opens its lockfile writable even for a reader; record the stock
        # refusal and run recovery on the isolated writable target after the
        # strictly read-only structural guard and cold equality have passed.
        readonly_supported = True
        try:
            first = native(reopen, readonly=True)
        except RuntimeError as error:
            assert 'Read-only file system' in str(error)
            readonly_supported = False
            first = native(reopen)
        second = native(reopen)
        assert first == second and copier.inventory(target) == before
        print(json.dumps({'image': image, 'coldCopy': receipt, 'nativeReopenQueryTwice': first,
                          'nativeReadersDidNotChangeFiles': True, 'nativeReadOnlySupported': readonly_supported, 'noNetworkOrProductionData': True}))


if __name__ == '__main__': main()
