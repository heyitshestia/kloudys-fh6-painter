async page => page.evaluate(async () => {
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const shape = x => ({ type: 1048677, type_word: 101, resource_family: "Primitives", resource_index: 1, color: [100, 160, 220, 255], data: [x, 0, 1, 1, 0, 0, 0] });
  const currentX = () => objectToShape(vinylObjects()[0], { includeEditorMeta: true }).data[0];
  const edit = () => { const o = vinylObjects()[0]; o.left += 37; o.setCoords(); pushHistory("revision regression"); };
  const originalFetch = window.fetch;
  const originalSetItem = Storage.prototype.setItem;
  const checks = [];
  try {
    await clearAutosave();
    await loadPayload({ shapes: [shape(0)] });
    currentProjectName = `revision-test-${Date.now()}`;
    edit();
    const capturedX = currentX();
    let release, reached;
    const entered = new Promise(resolve => { reached = resolve; });
    const gate = new Promise(resolve => { release = resolve; });
    window.fetch = async (...args) => {
      const result = await originalFetch(...args);
      if (args[0] === PROJECT_SAVE_API) { reached(); await gate; }
      return result;
    };
    const saving = saveProject();
    await entered;
    edit();
    selectObjects([vinylObjects()[0]], "save-race nudge");
    nudgeSelected(1, 0);
    const newerX = currentX();
    release();
    await saving;
    window.fetch = originalFetch;
    await flushPendingAutosave();
    assert(documentDirty, "Save marked an edit made during delivery as saved");
    const recovery = await readAutosavePayload();
    assert(recovery.shapes[0].data[0] === newerX, "Save discarded newer recovery");
    await refreshProjectBrowser();
    const entry = projectBrowserState.entries.find(e => e.title === currentProjectName);
    assert(entry, "Actual saved project missing");
    const saved = await (await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}`)).json();
    assert(saved.payload.shapes[0].data[0] === capturedX, "Saved file does not contain the captured revision");
    await loadProjectPayload(saved.payload, entry.title);
    assert(currentX() === capturedX && !documentDirty, "Saved artifact reopen failed");
    await recoverAutosavePayload(recovery);
    assert(currentX() === newerX, "Recovery artifact reopen lost the newer edit");
    checks.push("edit-during-save, actual saved-file reopen, recovery reopen");

    currentProjectName = `new-document-race-${Date.now()}`;
    let releaseNew, reachedNew;
    const enteredNew = new Promise(resolve => { reachedNew = resolve; });
    const gateNew = new Promise(resolve => { releaseNew = resolve; });
    window.fetch = async (...args) => {
      const result = await originalFetch(...args);
      if (args[0] === PROJECT_SAVE_API) { reachedNew(); await gateNew; }
      return result;
    };
    const savingOld = saveProject();
    await enteredNew;
    await loadPayload({ shapes: [shape(500)] });
    currentProjectName = "new-unsaved-document";
    edit();
    releaseNew();
    await savingOld;
    assert(currentProjectName === "new-unsaved-document" && documentDirty, "Old save clobbered a new document");
    window.fetch = originalFetch;
    checks.push("new-document-during-save");

    await clearAutosave();
    Storage.prototype.setItem = function(key, value) {
      if (key === AUTOSAVE_KEY) throw new DOMException("Synthetic quota failure", "QuotaExceededError");
      return originalSetItem.call(this, key, value);
    };
    window.fetch = (...args) => args[0] === EDITOR_AUTOSAVE_API && args[1]?.method === "POST"
      ? Promise.resolve(new Response("unavailable", { status: 503 })) : originalFetch(...args);
    edit();
    await flushPendingAutosave();
    assert(autosaveStatus.state === "failed" && documentDirty, "Dual recovery failure was reported as success");
    assert(!document.getElementById("status").textContent.includes("Recovery pending"), "Failure left pending success text");
    window.fetch = originalFetch;
    edit();
    await flushPendingAutosave();
    assert(autosaveStatus.serverOk && !autosaveStatus.browserOk, "App-folder fallback failed");
    checks.push("quota plus HTTP failure, app-folder fallback");
    Storage.prototype.setItem = originalSetItem;

    let releaseWrite, writeEntered;
    const enteredWrite = new Promise(resolve => { writeEntered = resolve; });
    const gateWrite = new Promise(resolve => { releaseWrite = resolve; });
    let first = true, requests = 0;
    window.fetch = async (...args) => {
      if (args[0] === EDITOR_AUTOSAVE_API && args[1]?.method === "POST") {
        requests++;
        if (first) { first = false; writeEntered(); await gateWrite; }
      }
      return originalFetch(...args);
    };
    edit();
    const pending = flushPendingAutosave();
    await enteredWrite;
    clearAutosave();
    for (let i = 0; i < 12; i++) { edit(); flushPendingAutosave(); }
    const latestX = currentX();
    releaseWrite();
    await pending;
    window.fetch = originalFetch;
    const newest = await readAutosavePayload();
    assert(requests === 2 && newest.shapes[0].data[0] === latestX, "Recovery queue did not coalesce to the newest revision");
    await clearAutosave();
    localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(newest));
    assert(await readAutosavePayload() === null, "Clear tombstone allowed old browser recovery");
    checks.push("write-clear-write ordering, coalescing, stale browser recovery rejected");

    localStorage.removeItem(AUTOSAVE_CLEAR_KEY);
    const legacy = { shapes: [shape(777)], saved_at: "2026-09-01T00:00:00Z", name: "Legacy recovery" };
    await fetch(EDITOR_AUTOSAVE_API, { method: "POST", headers: { ...EDITOR_MUTATION_HEADERS, "Content-Type": "application/json" }, body: JSON.stringify(legacy) });
    localStorage.setItem(AUTOSAVE_KEY, JSON.stringify({ ...legacy, shapes: [shape(888)], saved_at: "2026-09-02T00:00:00Z" }));
    const selectedLegacy = await readAutosavePayload();
    assert(selectedLegacy.shapes[0].data[0] === 888, "Legacy recovery did not prefer the newer timestamp");
    await recoverAutosavePayload(selectedLegacy);
    assert(currentX() === 888, "Legacy recovery did not reopen");
    checks.push("legacy timestamp ordering and real recovery");
    return { passed: true, checks };
  } finally {
    window.fetch = originalFetch;
    Storage.prototype.setItem = originalSetItem;
    await clearAutosave();
  }
})
