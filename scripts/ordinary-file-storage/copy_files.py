#!/usr/bin/env python3
"""Cold ordinary-file copy with complete byte/POSIX verification. Never changes source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct


def check_mode_acl(raw, mode):
    """Only Linux nfsd's exact projection of three POSIX mode entries is trivial.

    See fs/nfsd/nfs4acl.c: mask_from_posix and _posix_to_nfsv4_one.
    Named principals, inherited entries and additional rights remain rejected.
    """
    def mask(perm, allow=False, owner=False):
        value = (0x120080 | (0x40100 if owner else 0)) if allow else 0
        if perm & 4: value |= 1
        if perm & 2: value |= 6 | (0x40 if stat.S_ISDIR(mode) else 0)
        if perm & 1: value |= 0x20
        return value
    owner, group, other = (mode >> 6) & 7, (mode >> 3) & 7, mode & 7
    expected = []
    if ~owner & (group | other):
        expected.append((1,0,mask(~owner & (group | other)),b'OWNER@'))
    expected.extend([(0,0,mask(owner,True,True),b'OWNER@'),
                     (0,0,mask(group,True),b'GROUP@')])
    if ~group & other:
        expected.append((1,0,mask(~group & other),b'GROUP@'))
    expected.append((0,0,mask(other,True),b'EVERYONE@'))
    encoded = struct.pack('>I',len(expected))
    for typ, flags, rights, who in expected:
        encoded += struct.pack('>IIII',typ,flags,rights,len(who)) + who + b'\0' * (-len(who) % 4)
    if raw != encoded:
        raise ValueError('NFS ACL is not the exact POSIX mode projection')


def inventory(root):
    """Exclude only an empty ext4 lost+found. Refuse uncopyable metadata/state."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Invalid volume root')
    result = {}
    links = {}
    for parent, dirs, files in os.walk(root, followlinks=False):
        for p in [Path(parent), *(Path(parent) / name for name in files),
                  *(Path(parent) / name for name in dirs if (Path(parent) / name).is_symlink())]:
            rel = str(p.relative_to(root))
            info = p.lstat()
            attributes = set(os.listxattr(p, follow_symlinks=False))
            if 'system.nfs4_acl' in attributes:
                check_mode_acl(os.getxattr(p, 'system.nfs4_acl', follow_symlinks=False), info.st_mode)
                attributes.remove('system.nfs4_acl')
            if attributes:
                raise ValueError('Extended metadata needs separate qualification')
            row = {'mode': info.st_mode, 'uid': info.st_uid, 'gid': info.st_gid,
                   'mtimeNs': info.st_mtime_ns}
            if stat.S_ISREG(info.st_mode):
                with p.open('rb') as stream:
                    row.update(bytes=info.st_size, sha256=hashlib.file_digest(stream, 'sha256').hexdigest())
                links.setdefault((info.st_dev, info.st_ino), []).append(rel)
            elif stat.S_ISLNK(info.st_mode):
                row['link'] = os.readlink(p)
            elif not stat.S_ISDIR(info.st_mode):
                raise ValueError('Special file requires separate qualification')
            result[rel] = row
        if Path(parent) == root and 'lost+found' in dirs:
            lost = root / 'lost+found'
            if lost.is_symlink() or any(lost.iterdir()):
                raise ValueError('Unexpected filesystem recovery data')
            dirs.remove('lost+found')
    for paths in links.values():
        if (root / paths[0]).stat().st_nlink != len(paths):
            raise ValueError('Hard link escapes the copied tree')
        for rel in paths:
            result[rel]['hardlinks'] = sorted(paths)
    return result


def copy_files(source, target, marker, identity):
    if source != source.resolve(strict=True) or target != target.resolve(strict=True):
        raise ValueError('Redirected source/target path')
    if source == target or source in target.parents or target in source.parents:
        raise ValueError('Overlapping source/target')
    marker_path = source / marker
    if Path(marker).name != marker or marker_path.is_symlink() or not marker_path.is_file() or marker_path.stat().st_size > 128:
        raise ValueError('Invalid retained identity file')
    if marker_path.read_bytes() != identity.encode():
        raise ValueError('Wrong retained identity')
    if target.is_symlink() or not target.is_dir() or any(target.iterdir()):
        raise ValueError('Target must be an existing empty directory')
    before = inventory(source)
    first_links = {}
    for rel, row in sorted(before.items(), key=lambda item: (len(Path(item[0]).parts), item[0])):
        p, q = source / rel, target / rel
        mode = row['mode']
        if rel == '.':
            continue
        if stat.S_ISDIR(mode):
            q.mkdir(mode=0o700)
        elif stat.S_ISLNK(mode):
            q.symlink_to(row['link'])
        else:
            group = tuple(row['hardlinks'])
            if group in first_links:
                os.link(first_links[group], q)
            else:
                shutil.copyfile(p, q, follow_symlinks=False)
                with q.open('rb') as stream:
                    os.fsync(stream.fileno())
                first_links[group] = q
    # Set directories last; child creation must not alter verified timestamps.
    for rel, row in sorted(before.items(), key=lambda item: len(Path(item[0]).parts), reverse=True):
        q = target / rel
        os.chown(q, row['uid'], row['gid'], follow_symlinks=False)
        if not stat.S_ISLNK(row['mode']):
            os.chmod(q, stat.S_IMODE(row['mode']))
        os.utime(q, ns=(row['mtimeNs'], row['mtimeNs']), follow_symlinks=False)
        if stat.S_ISDIR(row['mode']):
            fd = os.open(q, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    if inventory(source) != before or inventory(target) != before:
        raise ValueError('Cold source or completed target comparison failed; preserve both')
    digest = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    return {'entries': len(before), 'bytes': sum(v.get('bytes', 0) for v in before.values()),
            'manifestSHA256': digest, 'bytesAndPosixMetadataEqual': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('marker')
    parser.add_argument('identity')
    args = parser.parse_args()
    source, target = args.source.absolute(), args.target.absolute()
    if not source.is_mount() or not target.is_mount() or not os.statvfs(source).f_flag & os.ST_RDONLY:
        parser.error('Use a retired read-only source mount and a separate target mount')
    print(json.dumps(copy_files(source, target, args.marker, args.identity)))
