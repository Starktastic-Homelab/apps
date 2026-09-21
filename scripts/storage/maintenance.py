"""Use the same immutable Ansible helper as infrastructure workflows."""
import os
from pathlib import Path


def require_maintenance():
    # Supplied by the workflow's pinned checkout, never downloaded at runtime.
    from maintenance_lock import verify
    verify(Path('/maintenance'), os.environ['MAINTENANCE_OWNER'], os.environ['MAINTENANCE_NONCE'])
