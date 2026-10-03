const fs = require('fs');
const crypto = require('crypto');
const assert = require('assert/strict');
const {execFileSync} = require('child_process');
const Filesystem = require('/home/csi/app/src/utils/filesystem').Filesystem;
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
async function main() {
  const helper = new Filesystem();
  const results = [];
  for (const [name, options] of [['control', ['-m','0']], ['blank-no-write', ['-m','0','-n']], ['unrecognized-no-write', ['-m','0','-n']]]) {
    const path = '/probe/'+name+'.img';
    const content = name.startsWith('unrecognized') ? Buffer.alloc(16*1024*1024, 0xa5) : Buffer.alloc(16*1024*1024);
    fs.writeFileSync(path, content);
    const before = hash(path);
    await helper.formatDevice(path, 'ext4', options);
    const after = hash(path);
    let type = '';
    try { type = execFileSync('blkid', ['-p','-s','TYPE','-o','value',path], {encoding:'utf8'}).trim(); } catch (err) { if (err.status !== 2) throw err; }
    const changed = before !== after;
    assert.equal(changed, name === 'control', name+' bytes changed unexpectedly');
    assert.equal(type, name === 'control' ? 'ext4' : '', name+' unexpected filesystem signature');
    results.push({name, before, after, changed, filesystem:type || null});
  }
  console.log(JSON.stringify({image:'ghcr.io/democratic-csi/democratic-csi@sha256:746bf6b373ae75f5da8b1e412d13c3e8d0e2e1494654268b9dd6fe1f1e55aade', scope:'real stock Filesystem.formatDevice helper; regular files only; not NodeStage', results},null,2));
}
main().catch(error => { console.error(error); process.exitCode=1; });
