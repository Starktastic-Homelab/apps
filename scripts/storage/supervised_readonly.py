"""Fixed JSON adapter for the qualified external runner; no mutation dispatch."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from storage_inspection import inspect_state, preflight


def observe(operation, root, service, *, helper_directory=None, dependency_directory=None):
    if operation not in ('status', 'preflight') or service != 'jellyfin':
        raise ValueError('Unsupported read-only request')
    if operation == 'status':
        return inspect_state(root, service, now=datetime.now(timezone.utc))
    return preflight(root, service, now=datetime.now(timezone.utc),
                     helper_directory=helper_directory, dependency_directory=dependency_directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['status', 'preflight'])
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--service', choices=['jellyfin'], required=True)
    parser.add_argument('--helper-directory', type=Path, help='Executor-selected verified helper directory')
    parser.add_argument('--dependency-directory', type=Path, help='Executor-selected verified dependency directory')
    args = parser.parse_args()
    report = observe(args.operation, args.state_root, args.service,
                     helper_directory=args.helper_directory, dependency_directory=args.dependency_directory)
    print(json.dumps(report))
    return int(any(check['status'] in ('fail', 'unknown') for check in report['checks']))


if __name__ == '__main__': raise SystemExit(main())
