"""Fixed JSON adapter for the qualified external runner; no mutation dispatch."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from storage_inspection import inspect_state, preflight


def observe(operation, root, service):
    if operation not in ('status', 'preflight') or service != 'jellyfin':
        raise ValueError('Unsupported read-only request')
    inspector = inspect_state if operation == 'status' else preflight
    return inspector(root, service, now=datetime.now(timezone.utc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['status', 'preflight'])
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--service', choices=['jellyfin'], required=True)
    args = parser.parse_args()
    report = observe(args.operation, args.state_root, args.service)
    print(json.dumps(report))
    return int(any(check['status'] in ('fail', 'unknown') for check in report['checks']))


if __name__ == '__main__': raise SystemExit(main())
