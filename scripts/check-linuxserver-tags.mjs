import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const { packageRules } = JSON.parse(readFileSync(new URL('../renovate.json', import.meta.url), 'utf8'));
const linuxserver = packageRules.find(rule => rule.matchPackageNames?.includes('/^lscr\\.io/linuxserver//'));
const qbittorrent = packageRules.find(rule => rule.matchPackageNames?.includes('lscr.io/linuxserver/qbittorrent'));

// ponytail: smoke-test policy filters; Renovate owns version comparison.
assert.equal(linuxserver.versioning, 'loose');
const fullTag = new RegExp(linuxserver.extractVersion);
assert.equal(fullTag.exec('v1.2.3.4-ls5')?.groups?.version, 'v1.2.3.4-ls5');
assert.doesNotMatch('438eee94-ls46', fullTag);
assert.doesNotMatch('1.2rc1-ls4', fullTag);
for (const tag of ['latest', '1.2.3', 'nightly-1.2.3-ls4', 'amd64-1.2.3-ls4', '1.2.3-beta-ls4']) {
  assert.doesNotMatch(tag, fullTag);
}

assert.match(linuxserver.allowedVersions, /^!\/.*\/$/);
const legacyUbuntu = new RegExp(linuxserver.allowedVersions.slice(2, -1));
assert.match('24.04.1-ls1', legacyUbuntu);
assert.doesNotMatch('12.1ubu2604-ls50', legacyUbuntu);

const qbitAllowed = new RegExp(qbittorrent.allowedVersions.slice(1, -1));
assert.match('5.2.3_v2.0.14-ls1', qbitAllowed);
assert.doesNotMatch('6.0.0_v2.0.14-ls1', qbitAllowed);
assert.doesNotMatch('5.2.3_v1.2.20-ls1', qbitAllowed);
assert.doesNotMatch('5.2.3_v3.0.0-ls1', qbitAllowed);
console.log('LinuxServer full-tag policy checks passed');
