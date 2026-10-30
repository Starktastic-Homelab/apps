"""Build OCI import archives without changing pinned image manifest blobs."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile

root=pathlib.Path(sys.argv[1]);pins=json.loads(pathlib.Path(sys.argv[2]).read_text())
crane=sys.argv[3]
pairs=[(v['pinned_reference'],root/f'csi-{i}.tar') for i,v in enumerate(pins['images'])]
pairs.append((json.loads((root/'fixture-image.json').read_text())['pinned_reference'],root/'sqlite-fixture.tar'))
for ref,dest in pairs:
    layout=dest.with_suffix('.oci.tar')
    if layout.exists(): shutil.rmtree(layout)
    subprocess.run([crane,'pull','--platform','linux/amd64','--format=oci','--annotate-ref',ref,str(layout)],check=True,stdout=subprocess.DEVNULL)
    index=json.loads((layout/'index.json').read_text());assert len(index['manifests'])==1
    descriptor=index['manifests'][0];assert descriptor['digest']==ref.split('@')[1]
    original=descriptor['annotations']['org.opencontainers.image.ref.name']
    assert original.replace('index.docker.io/','docker.io/',1)==ref
    # Normalize Docker Hub's alias in archive metadata, preserving the image blob.
    descriptor['annotations']['org.opencontainers.image.ref.name']=ref
    (layout/'index.json').write_text(json.dumps(index))
    body=(layout/'blobs/sha256'/ref.split(':')[-1]).read_bytes()
    assert hashlib.sha256(body).hexdigest()==ref.split(':')[-1]
    tmp=dest.with_suffix('.verified.tar')
    with tarfile.open(tmp,'w') as t:
        for entry in sorted(layout.iterdir()):t.add(entry,arcname=entry.name)
    tmp.replace(dest);shutil.rmtree(layout)
    print('Verified OCI archive: '+ref.split('@')[0],flush=True)
