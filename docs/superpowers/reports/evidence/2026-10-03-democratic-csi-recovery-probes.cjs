// Pinned upstream methods, synthetic storage only. No network, subprocesses or mounts.
// Usage: node <this-file> <democratic-csi-v1.9.5-source-directory>
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createHash } = require('node:crypto');
const root = process.argv[2];
assert(root, 'Pass the pinned democratic-csi v1.9.5 source directory');
const hashes = {
  'src/driver/index.js': 'dbea0320800ea044cb9c185cf7281c7d85a9d7d7a295fe4e1968ffdc0cdec9be',
  'src/driver/controller-zfs/index.js': '656d59a205a4dc8af7930afd2f6cc10352bd053ae67e9ab7104bc3c1c7f40531',
  'src/driver/freenas/api.js': '37b0dcc5c21800c8e75d6acaadd6c3ad7409ed8ad234e8862c14e3afef7400a3',
  'src/driver/freenas/http/api.js': 'd58e1bf5329888087fa0123720863e31efb8345a76fa0084d8dc8205d8385457',
};
const sources = {};
for (const [file, hash] of Object.entries(hashes)) {
  const source = fs.readFileSync(path.join(root, file), 'utf8');
  assert.equal(createHash('sha256').update(source).digest('hex'), hash, file);
  sources[file] = source;
}
class GrpcError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}
const globals = {
  GrpcError,
  grpc: { status: Object.fromEntries(['INVALID_ARGUMENT', 'FAILED_PRECONDITION',
    'OUT_OF_RANGE', 'ALREADY_EXISTS'].map(x => [x, x])) },
  _: { get: (obj, key, fallback) => key.split('.').reduce((v, k) => v?.[k], obj) ?? fallback },
};
// Extract whole methods between class-level boundaries; do not modify their bodies.
function method(file, name) {
  const source = sources[file];
  const start = source.indexOf(`  async ${name}(`);
  assert(start >= 0, name);
  const match = /\n  (?:async \w+\(|\/\*\*)/.exec(source.slice(start + 1));
  assert(match, `${name} boundary`);
  const text = source.slice(start, start + 1 + match.index);
  const constants = {};
  for (const m of source.matchAll(/const ([A-Z_]+)\s*=\s*("[^"]*");/g)) {
    constants[m[1]] = JSON.parse(m[2]);
  }
  return vm.runInNewContext(`({${text}})`, { ...globals, ...constants })[name];
}
const base = 'src/driver/index.js';
const apiFile = 'src/driver/freenas/api.js';
const zfsFile = 'src/driver/controller-zfs/index.js';
const httpFile = 'src/driver/freenas/http/api.js';
const getId = method(base, 'getVolumeIdFromCall');
const creates = { truenas_api: method(apiFile, 'CreateVolume'), zfs_cli: method(zfsFile, 'CreateVolume') };
const GiB = 1024 ** 3;
function request(name) {
  return { request: { name, parameters: {
    'csi.storage.k8s.io/pvc/namespace': 'media',
    'csi.storage.k8s.io/pvc/name': 'config',
  }, capacity_range: { required_bytes: GiB },
  volume_capabilities: [{ mount: { fs_type: 'ext4' }, access_mode: { mode: 'SINGLE_NODE_WRITER' } }] } };
}
function fixture(kind, failure) {
  // Simulated retained volume with data, surviving loss of Kubernetes objects.
  const datasets = new Map([['tank/test/pvc-old-uid', { size: GiB, sentinel: 'original-data' }]]);
  const allocations = [];
  const mutations = [];
  const lookup = (name) => {
    if (failure) throw new Error(failure);
    if (!datasets.has(name)) throw new Error('dataset does not exist');
    return datasets.get(name);
  };
  const allocate = (name, size) => {
    mutations.push(['create', name]);
    if (!datasets.has(name)) {
      allocations.push(name);
      datasets.set(name, { size, sentinel: 'empty-fixture' });
    }
  };
  const set = async (name, props) => {
    mutations.push(['set', name]);
    if (props.volsize) datasets.get(name).size = props.volsize;
  };
  const http = {
    get: async (endpoint) => {
      if (failure === 'timeout') throw new Error('timeout');
      if (failure) return { statusCode: Number(failure), body: { error: 'access/backend failure' } };
      const name = decodeURIComponent(endpoint.split('/id/')[1]);
      if (!datasets.has(name)) return { statusCode: 404 };
      return { statusCode: 200, body: { volsize: { rawvalue: String(datasets.get(name).size) } } };
    },
    post: async (_endpoint, data) => {
      const exists = datasets.has(data.name);
      allocate(data.name, data.volsize);
      return exists ? { statusCode: 422, body: { error: 'already exists' } } : { statusCode: 200 };
    },
  };
  const api = {
    getHttpClient: async () => http,
    DatasetGet: method(httpFile, 'DatasetGet'),
    DatasetCreate: method(httpFile, 'DatasetCreate'),
    DatasetSet: set,
    normalizeProperties: (body) => body,
    getSystemProperties: (props) => Object.fromEntries(Object.entries(props).filter(([k]) => !k.includes(':'))),
    getUserProperties: (props) => Object.fromEntries(Object.entries(props).filter(([k]) => k.includes(':'))),
    getPropertiesKeyValueArray: (props) => Object.entries(props).map(([key, value]) => ({ key, value })),
  };
  const options = { driver: kind === 'truenas_api' ? 'freenas-api-iscsi' : 'zfs-generic-iscsi', zfs: {} };
  const driver = {
    options,
    ctx: { logger: { debug() {} } },
    getDriverZfsResourceType: () => 'volume',
    getDriverShareType: () => 'iscsi',
    getExecClient: () => ({}),
    getTrueNASHttpApiClient: async () => api,
    getZetabyte: async () => ({
      helpers: { generateZvolSize: (size) => size },
      zfs: {
        get: async (name) => ({ [name]: { volsize: { value: String(lookup(name).size) } } }),
        create: async (name, config) => allocate(name, config.size),
        set,
      },
    }),
    getNormalizedParameters: () => ({}),
    getMergedDriverOptions: () => options,
    getVolumeParentDatasetName: () => 'tank/test',
    getDetachedSnapshotParentDatasetName: () => 'tank/snapshots',
    getMinimumVolumeSize: async () => 0,
    getMaxZvolNameLength: async () => 255,
    getVolumeIdFromCall: getId,
    assertCapabilities: () => ({ valid: true }),
    // Export creation is deliberately outside this probe; do not infer real target behavior.
    createShare: async (_call, name) => ({ node_attach_driver: 'iscsi', iqn: `iqn.synthetic:${name}` }),
  };
  return { datasets, allocations, mutations, driver, create: creates[kind] };
}
async function main() {
  const findings = {};
  for (const kind of Object.keys(creates)) {
    const same = fixture(kind);
    const old = await same.create.call(same.driver, request('pvc-old-uid'));
    assert.equal(old.volume.volume_id, 'pvc-old-uid');
    assert.equal(same.allocations.length, 0);
    assert.equal(same.datasets.get('tank/test/pvc-old-uid').sentinel, 'original-data');
    const fresh = await same.create.call(same.driver, request('pvc-new-uid'));
    assert.equal(fresh.volume.volume_id, 'pvc-new-uid');
    assert.deepEqual(same.allocations, ['tank/test/pvc-new-uid']);
    assert.equal(same.datasets.get('tank/test/pvc-old-uid').sentinel, 'original-data');
    assert.equal(same.datasets.get('tank/test/pvc-new-uid').sentinel, 'empty-fixture');

    const errors = kind === 'truenas_api' ? ['403', '500', 'timeout'] : ['permission denied', 'connection timeout'];
    for (const error of errors) {
      const denied = fixture(kind, error);
      await assert.rejects(() => denied.create.call(denied.driver, request('pvc-new-uid')));
      assert.equal(denied.mutations.length, 0, `${kind}: ${error} must block before mutations`);
    }
    const missing = fixture(kind);
    missing.datasets.clear();
    await missing.create.call(missing.driver, request('pvc-old-uid'));
    assert.deepEqual(missing.allocations, ['tank/test/pvc-old-uid']);
    findings[kind] = {
      same_request_name: 'Original synthetic data retained; export behavior mocked',
      same_pvc_name_new_uid: 'New dataset requested; original retained dataset untouched',
      lookup_errors: `${errors.join(', ')} rejected before mutations`,
      missing_original_same_request_name: 'New dataset requested; no recovery-only guard',
    };
  }
  console.log(JSON.stringify({ evidence: 'synthetic source behavior only; no Kubernetes, NAS or node-stage execution', findings }, null, 2));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
