"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const workers = [];
class FakeWorker {
  constructor() { this.messages = []; workers.push(this); }
  postMessage(message) {
    this.messages.push(structuredClone(message));
    if (!this.hold) queueMicrotask(() => this.onmessage({ data: { id: message.id, value: { ok: true } } }));
  }
  terminate() { this.terminated = true; }
}
const scope = { Worker: FakeWorker, setTimeout, clearTimeout, window: {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../editor-persistence.js"), "utf8"), scope);

async function run() {
  const persistence = scope.window.KfpsEditorPersistence.create({});
  const payload = data => ({ shapes: [], editor_source_overlay: { data_url: data, svg_text: null, transform: { left: 1 } } });
  await persistence.request("recovery", { payload: payload("same reference") });
  const oldCachedObject = persistence.lastReference;
  await persistence.request("recovery", { payload: payload(["same", "reference"].join(" ")) });
  assert.notEqual(persistence.lastReference, oldCachedObject, "Reopening identical reference text must release the previous cache object");
  assert.equal(persistence.lastReference.data_url, "same reference");
  assert.equal(Object.hasOwn(workers[0].messages[1], "reference"), false, "Rebinding must not resend unchanged reference bytes");
  assert.equal(workers[0].messages[1].payload.editor_source_overlay.data_url, null);
  assert.equal(workers[0].messages[1].payload.editor_source_overlay.transform.left, 1);
  await persistence.request("recovery", { payload: payload("changed reference") });
  assert.equal(workers[0].messages[2].reference.data_url, "changed reference");
  workers[0].hold = true;
  const pending = Array.from({ length: 8 }, () => persistence.request("recovery", { payload: payload("changed reference") }));
  await assert.rejects(persistence.request("recovery"), /Background storage is busy/);
  const settled = Promise.allSettled(pending);
  persistence.reset(new Error("Injected worker interruption"));
  assert.ok((await settled).every(result => result.status === "rejected"));
  assert.equal(persistence.pending.size, 0);
  assert.equal(persistence.lastReference, undefined);
  assert.equal(workers[0].terminated, true);
  await persistence.request("recovery", { payload: payload("changed reference") });
  assert.equal(workers[1].messages[0].reference.data_url, "changed reference", "A restarted worker must receive the reference again");
  persistence.reset(new Error("test complete"));
  console.log("Persistence: reference rebinding/deduplication, queue bounds and worker restart passed.");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
