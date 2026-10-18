// Exact Immich image's installed BullMQ; synthetic names/data only.
const { Queue, Worker } = require('/usr/src/app/server/node_modules/bullmq');
const assert = require('node:assert/strict');
const connection = { host: '127.0.0.1', port: 6379, password: 'synthetic-fixture-only', maxRetriesPerRequest: null };
(async () => {
  const queue = new Queue('synthetic-retained-jobs', { connection });
  const worker = new Worker('synthetic-retained-jobs', async () => {}, {
    connection, autorun: false, lockDuration: 600000,
  });
  if (process.argv[2] === 'seed') {
    await queue.add('active', { payload: '\u0000שלום' }, { jobId: 'job-active' });
    await queue.add('pending', { payload: 'pending' }, { jobId: 'job-pending' });
    const job = await worker.getNextJob('synthetic-token', { block: false });
    assert.equal(job.id, 'job-active');
    assert.equal(await job.getState(), 'active');
  } else {
    const active = await queue.getJob('job-active');
    const pending = await queue.getJob('job-pending');
    assert.deepEqual(active.data, { payload: '\u0000שלום' });
    assert.deepEqual(pending.data, { payload: 'pending' });
    assert.equal(await active.getState(), 'active');
    assert.equal(await pending.getState(), 'waiting');
    await active.moveToCompleted('recovered', 'synthetic-token', false);
    const job = await worker.getNextJob('synthetic-next', { block: false });
    assert.equal(job.id, 'job-pending');
    await job.moveToCompleted('recovered', 'synthetic-next', false);
    assert.equal(await queue.getCompletedCount(), 2);
  }
  await worker.close(true);
  await queue.close();
  process.stdout.write(JSON.stringify({ qualified: true }) + '\n');
})().catch(error => { console.error(error); process.exit(1); });
