"""Lab-scoped kubectl and fsynced operation receipts; never use default context."""
import json
import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
PRIVATE = ROOT / '.runtime'
ENV = dict(os.environ, KUBECONFIG=str(PRIVATE / 'kubeconfig'))

def kubectl(*args, data=None, check=True):
    result = subprocess.run(['kubectl', *args], input=None if data is None else json.dumps(data),
                            text=True, capture_output=True, env=ENV, check=False)
    if check and result.returncode:
        raise RuntimeError(result.stderr)
    return result

def apply(items):
    return kubectl('apply', '--server-side', '--field-manager=iscsi-rehearsal', '-f', '-',
                   data={'apiVersion':'v1','kind':'List','items':items})

def receipt(event):
    with (PRIVATE / 'operations.jsonl').open('a') as f:
        f.write(json.dumps(event)+'\n')
        f.flush()
        os.fsync(f.fileno())
