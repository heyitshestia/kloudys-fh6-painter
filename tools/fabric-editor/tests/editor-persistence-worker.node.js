"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

async function main() {
  const requests = [];
  const headers = { "Content-Type": "application/json", "X-KFPS-Editor-Request": "worker-test" };
  const config = { headers, maxBytes: 100 * 1024 * 1024 };
  const context = vm.createContext({
    Blob, TextEncoder, TextDecoder, AbortSignal, crypto: webcrypto,
    setTimeout, clearTimeout, self: {},
    indexedDB: { open() { throw new Error("Browser storage unavailable in this fixture"); } },
    fetch: async (url, options) => {
      requests.push({ url, options });
      assert.equal(options.method, "POST");
      assert.equal(options.headers["X-KFPS-Editor-Request"], headers["X-KFPS-Editor-Request"]);
      assert.equal(options.headers["Content-Type"], "application/json");
      assert.ok(options.signal instanceof AbortSignal, "network operation must have a deadline");
      const sha256 = new URL(url, "http://localhost").searchParams.get("sha256");
      const result = sha256 ? { ok: true, sha256, size: options.body.size } : { ok: true, applied: true };
      return { ok: true, json: async () => result };
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../editor-persistence-worker.js"), "utf8"), context);
  const source = { data_url: "data:image/png;base64,AAAA", svg_text: null };
  const reference = context.prepareReference(source);
  const payload = { shapes: [], editor_source_overlay: { visible: true }, recovery_revision: 1 };
  const recovery = await context.execute({ operation: "recovery", payload, config }, reference);
  assert.equal(recovery.serverOk, true);
  assert.equal(recovery.browserOk, false, "browser failure must not block the independent app copy");
  await context.execute({ operation: "recovery", payload: { ...payload, recovery_revision: 2 }, config }, reference);
  await context.execute({ operation: "recovery", payload: { action: "clear", shapes: [], recovery_revision: 3 }, config }, null);
  await context.execute({ operation: "saveProject", payload, config, name: "Worker request", overwrite: false }, reference);
  assert.deepEqual(requests.map(({ url }) => url.split("?")[0]), [
    "/api/fabric-editor/recovery-reference", "/api/fabric-editor/autosave",
    "/api/fabric-editor/autosave", "/api/fabric-editor/autosave", "/api/fabric-editor/save-project",
  ], "all worker mutation paths must be exercised; an unchanged reference is uploaded once");
  const checkpoint = JSON.parse(requests[1].options.body);
  assert.match(checkpoint.editor_recovery_reference.sha256, /^[a-f0-9]{64}$/);
  assert.equal(checkpoint.editor_source_overlay.data_url, undefined, "checkpoints must not repeat reference bytes");
  const project = JSON.parse(await requests[4].options.body.text());
  assert.equal(project.payload.editor_source_overlay.data_url, source.data_url);
  assert.equal(project.overwrite, false);
  assert.equal(project.name, "Worker request");
  await assert.rejects(context.execute({ operation: "saveProject", payload, name: "Large", config: { ...config, maxBytes: 1 } }, reference), /save limit/);
  assert.equal(requests.length, 5, "over-budget project must not issue a write");
  console.log("Persistence worker: authenticated and bounded project, recovery, reference and clear requests passed.");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
