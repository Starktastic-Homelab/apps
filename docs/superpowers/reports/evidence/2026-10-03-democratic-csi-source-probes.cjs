// Source-only probes. No network, subprocess, storage, or privileged operation.
// Usage: node <this-file> <democratic-csi-v1.9.5-source-directory>
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createHash } = require('node:crypto');
const { EventEmitter } = require('node:events');

const root = process.argv[2];
assert(root, 'Pass the pinned democratic-csi v1.9.5 source directory');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const marker = 'SYNTHETIC-NOT-A-CREDENTIAL';
const findings = {};
const hashes = {
  'src/utils/iscsi.js': '8ceeb7080dd76a63e2de2d8d7af48c9e59d6dada368d8614e3c4e2bb46a0710e',
  'src/driver/controller-zfs-generic/index.js': '381a055c08d32708acf7298e61af3b8f1f6c530b72cad379ed44feb62483c46a',
  'src/driver/freenas/api.js': '37b0dcc5c21800c8e75d6acaadd6c3ad7409ed8ad234e8862c14e3afef7400a3',
};
for (const [file, expected] of Object.entries(hashes)) {
  assert.equal(createHash('sha256').update(read(file)).digest('hex'), expected,
    `Source differs from inspected v1.9.5: ${file}`);
}

async function main() {
  const argv = [];
  const logs = [];
  const module = { exports: {} };
  vm.runInNewContext(read('src/utils/iscsi.js'), {
    module,
    process: { env: {} },
    console: { log: (...args) => logs.push(args.join(' ')) },
    require: (name) => {
      assert(['child_process', './general', 'net'].includes(name));
      return {}; // Every external operation is absent; spawn is injected below.
    },
  });
  const iscsi = new module.exports.ISCSI({ executor: {
    spawn: (_command, args) => {
      argv.push([...args]);
      const child = new EventEmitter();
      child.stdout = new EventEmitter();
      child.stderr = new EventEmitter();
      queueMicrotask(() => child.emit('close', 0));
      return child;
    },
  } });
  await iscsi.iscsiadm.createNodeDBEntry('iqn.synthetic', '192.0.2.1', {
    'node.session.auth.password': marker,
  });
  assert(argv.some((args) => args.includes(marker)));
  assert(!logs.join('\n').includes(marker));
  findings.node = 'CHAP marker reaches mocked spawn arguments; command log redacts it';

  const generic = read('src/driver/controller-zfs-generic/index.js');
  const method = generic.slice(generic.indexOf('  async targetCliCommand(data)'),
    generic.indexOf('  async nvmetCliCommand(data)'));
  assert(method.startsWith('  async targetCliCommand(data)'));
  let remoteCommand;
  const targetLogs = [];
  const driver = {
    options: {},
    ctx: { logger: { verbose: (message) => targetLogs.push(message) } },
    targetCliMutex: { runExclusive: (fn) => fn() },
    getExecClient: () => ({
      buildCommand: (command, args) => [command, ...args].join(' '),
      exec: async (command) => {
        remoteCommand = command;
        return { code: 0, stdout: '', stderr: '' };
      },
    }),
  };
  const target = vm.runInNewContext(`({${method}})`, {
    _: { get: (_object, _key, fallback) => fallback },
  });
  await target.targetCliCommand.call(driver, `cd /iscsi/example/tpg1\nset auth password=${marker}\ncd /`);
  assert(remoteCommand.includes(marker));
  assert(!targetLogs.join('\n').includes(marker));
  findings.target = 'CHAP marker reaches mocked remote shell command; command log redacts it';

  const api = read('src/driver/freenas/api.js');
  const start = api.indexOf('  async ListVolumes(call)');
  const end = api.indexOf('\n  /**', start);
  assert(start >= 0 && end > start);
  const list = vm.runInNewContext(`({${api.slice(start, end)}})`, {});
  const observer = {
    getDriverZfsResourceType: () => 'volume',
    getHttpClient: async () => ({ get: async () => ({ statusCode: 403 }) }),
    getTrueNASHttpApiClient: async () => ({}),
    getZetabyte: async () => ({}),
    getVolumeParentDatasetName: () => 'tank/synthetic',
    ctx: { logger: { debug: () => {} } },
  };
  const result = await list.ListVolumes.call(observer, { request: { max_entries: 0 } });
  assert.equal(result.entries.length, 0);
  findings.listVolumes = 'Mocked HTTP 403 returns an empty volume list instead of an error';
  console.log(JSON.stringify({ evidence: 'synthetic source behavior only', findings }, null, 2));
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
