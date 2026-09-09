async page => page.evaluate(async () => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const originalFetch = window.fetch;
  const assert = (v, m) => { if (!v) throw new Error(m); };
  let releaseStalledWrite;
  try {
    await clearAutosave();
    await loadPayload({ shapes: [{ type: 1048677, color: [20, 90, 210, 255], data: [64, 0, 1, 1, 0, 0, 0] }] });
    await flushPendingAutosave();
    let loseResponse = true;
    window.fetch = async (...args) => {
      const response = await originalFetch(...args);
      if (loseResponse && args[0] === EDITOR_AUTOSAVE_API && args[1]?.method === "POST") {
        loseResponse = false;
        throw new TypeError("Synthetic response loss after server committed");
      }
      return response;
    };
    vinylObjects()[0].left += 7; vinylObjects()[0].setCoords(); pushHistory("response loss");
    await flushPendingAutosave();
    assert(!autosaveStatus.serverOk, "Response loss did not reach failure path");
    await sleep(2500);
    assert(autosaveStatus.serverOk, "Identical committed revision was not acknowledged on retry");
    window.fetch = (url, options) => url === EDITOR_AUTOSAVE_API && !options?.method
      ? new Promise((resolve, reject) => options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true }))
      : originalFetch(url, options);
    const start = performance.now();
    const recovered = await readAutosavePayload();
    const readMs = performance.now() - start;
    assert(recovered?.shapes.length === 1 && readMs >= 4900 && readMs < 6500, "Stalled server blocked browser recovery fallback");
    window.fetch = originalFetch;
    let enteredWrite;
    const entered = new Promise(resolve => { enteredWrite = resolve; });
    const gate = new Promise(resolve => { releaseStalledWrite = resolve; });
    let firstWrite = true, activeWrites = 0, maxActiveWrites = 0;
    window.fetch = async (...args) => {
      if (args[0] !== EDITOR_AUTOSAVE_API || args[1]?.method !== "POST") return originalFetch(...args);
      activeWrites++;
      maxActiveWrites = Math.max(maxActiveWrites, activeWrites);
      try {
        if (firstWrite) { firstWrite = false; enteredWrite(); await gate; }
        return await originalFetch(...args);
      } finally { activeWrites--; }
    };
    vinylObjects()[0].left += 11; vinylObjects()[0].setCoords(); pushHistory("stalled older write");
    const pending = flushPendingAutosave();
    await entered;
    vinylObjects()[0].left += 13; vinylObjects()[0].setCoords(); pushHistory("newer edit during stalled write");
    const expectedX = objectToShape(vinylObjects()[0], { includeEditorMeta: true }).data[0];
    const backupStarted = performance.now();
    await sleep(900);
    const browserCopy = JSON.parse(localStorage.getItem(AUTOSAVE_KEY) || "null");
    assert(browserCopy?.shapes[0].data[0] === expectedX, "Stalled app-folder write postponed the newer browser recovery");
    assert(autosaveStatus.browserOk && !autosaveStatus.serverOk, "Pending server response hid the available browser recovery");
    const browserBackupMs = performance.now() - backupStarted;
    releaseStalledWrite();
    await pending;
    window.fetch = originalFetch;
    const serverCopy = await (await originalFetch(EDITOR_AUTOSAVE_API)).json();
    assert(serverCopy.payload?.shapes[0].data[0] === expectedX && maxActiveWrites === 1, "Stalled recovery completion violated ordered latest-write delivery");
    return { committedWriteRetryPassed: true, stalledReadFallbackMs: readMs, stalledWriteBrowserBackupMs: browserBackupMs, orderedWrites: true };
  } finally { releaseStalledWrite?.(); window.fetch = originalFetch; await clearAutosave(); }
})
