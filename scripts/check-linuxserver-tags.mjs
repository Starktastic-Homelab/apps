import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const config = JSON.parse(readFileSync(new URL('../renovate.json', import.meta.url), 'utf8'));
const commonRule = config.packageRules.find(rule => rule.matchPackageNames?.includes('/^lscr\\.io/linuxserver//'));
const arrRule = config.packageRules.find(rule => rule.matchPackageNames?.includes('lscr.io/linuxserver/sonarr'));
const qbitRule = config.packageRules.find(rule => rule.matchPackageNames?.includes('lscr.io/linuxserver/qbittorrent'));

function versionRegex(rule) {
  assert.ok(rule?.versioning?.startsWith('regex:'), 'Missing LinuxServer regex versioning');
  return new RegExp(rule.versioning.slice(6));
}

const common = versionRegex(commonRule);
const arr = versionRegex(arrRule);
assert.deepEqual(commonRule.matchDatasources, ['docker']);
assert.deepEqual(arrRule.matchDatasources, ['docker']);
assert.deepEqual([...arrRule.matchPackageNames].sort(), [
  'lscr.io/linuxserver/lidarr',
  'lscr.io/linuxserver/prowlarr',
  'lscr.io/linuxserver/radarr',
  'lscr.io/linuxserver/sonarr'
]);

// ponytail: check captures here; use a Renovate dry run for actual update selection.
for (const [pattern, tag, expected] of [
  [common, 'v1.6.1-ls364', [1, 6, 1, 364, 0]],
  [common, '10.11.11ubu2604-ls47', [10, 11, 11, 47, 0]],
  [common, '12.1ubu2604-ls50', [12, 1, 0, 50, 0]],
  [common, '12.1ubu2604-ls9', [12, 1, 0, 9, 0]],
  [common, '12.1ubu2604-ls10', [12, 1, 0, 10, 0]],
  [common, '5.2.3_v2.0.14-ls476', [5, 2, 3, 476, 0]],
  [common, '5.2.3_v2.0.15-ls477', [5, 2, 3, 477, 0]],
  [common, 'v1.11.2-ls144', [1, 11, 2, 144, 0]],
  [arr, '3.1.0.4875-ls22', [3, 1, 0, 4875, 22]],
  [arr, '2.5.2.5491-ls159', [2, 5, 2, 5491, 159]],
  [arr, '4.0.19.2979-ls324', [4, 0, 19, 2979, 324]],
  [arr, '4.0.19.2980-ls325', [4, 0, 19, 2980, 325]],
  [arr, '6.3.0.10514-ls316', [6, 3, 0, 10514, 316]]
]) {
  const groups = pattern.exec(tag)?.groups;
  assert.ok(groups?.build, `Missing build capture: ${tag}`);
  assert.deepEqual(
    ['major', 'minor', 'patch', 'build', 'revision'].map(key => Number(groups[key] ?? 0)),
    expected,
    tag
  );
}

for (const tag of [
  'latest',
  '10.11.11',
  '12.1',
  'version-12.1ubu2604',
  'nightly-12.1ubu2604-ls50',
  'develop-4.0.19.2979-ls324',
  'amd64-12.1ubu2604-ls50',
  'arm64v8-12.1ubu2604-ls50',
  'libtorrentv1-5.2.3_v1.2.20-ls132',
  'v1.6.1-beta-ls364'
]) {
  assert.equal(common.test(tag) || arr.test(tag), false, tag);
}

assert.equal(common.exec('5.2.3_v2.0.14-ls476').groups.compatibility, '2');
assert.equal(common.exec('5.2.3_v1.2.20-ls477').groups.compatibility, '1');
assert.equal(common.exec('5.2.3_v3.0.0-ls477').groups.compatibility, '3');

assert.ok(qbitRule.allowedVersions.startsWith('/') && qbitRule.allowedVersions.endsWith('/'));
const qbitAllowed = new RegExp(qbitRule.allowedVersions.slice(1, -1));
assert.equal(qbitAllowed.test('5.2.3_v2.0.14-ls476'), true);
assert.equal(qbitAllowed.test('6.0.0_v2.0.14-ls1'), false);
assert.equal(qbitAllowed.test('10.0.0_v2.0.14-ls1'), false);

assert.ok(commonRule.allowedVersions.startsWith('!/') && commonRule.allowedVersions.endsWith('/'));
const legacyUbuntu = new RegExp(commonRule.allowedVersions.slice(2, -1));
assert.equal(legacyUbuntu.test('20.04.1-ls1'), true);
assert.equal(legacyUbuntu.test('12.1ubu2604-ls50'), false);
console.log('LinuxServer full-tag policy checks passed');
