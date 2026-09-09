async page => page.evaluate(async () => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const assert = (v, m) => { if (!v) throw new Error(m); };
  const originalFetch = window.fetch;
  const writes = [];
  let failNext = false;
  try {
    await clearAutosave();
    await loadPayload({ shapes: [{ type: 1048677, color: [180, 70, 100, 255], data: [0, 0, 1, 1, 0, 0, 0] }] });
    const edit = () => { vinylObjects()[0].left++; vinylObjects()[0].setCoords(); pushHistory("continuous editing"); };
    window.fetch = (...args) => {
      if (args[0] === EDITOR_AUTOSAVE_API && args[1]?.method === "POST") {
        const payload = JSON.parse(args[1].body);
        if (payload.action !== "clear") writes.push({ time: performance.now(), revision: payload.recovery_revision });
        if (failNext) { failNext = false; return Promise.resolve(new Response("unavailable", { status: 503 })); }
      }
      return originalFetch(...args);
    };
    const start = performance.now();
    for (let i = 0; i < 32; i++) { edit(); await sleep(100); }
    assert(writes.length >= 1 && writes[0].time - start < 2600, "Continuous edits starved recovery");
    await sleep(800);
    assert(autosaveStatus.state === "saved" && writes.length >= 2, "Quiet-time recovery did not complete");
    const continuousWrites = writes.length;
    failNext = true;
    edit();
    await flushPendingAutosave();
    assert(autosaveStatus.browserOk && !autosaveStatus.serverOk, "Browser fallback was not identified");
    await sleep(2500);
    assert(autosaveStatus.serverOk, "Temporary server failure was not retried without another edit");
    assert(document.getElementById("status").textContent.includes("Recovery saved in KFPS"), "Retry left a stale fallback status");
    edit();
    window.dispatchEvent(new Event("blur"));
    await drainAutosaveQueue();
    const recovered = await readAutosavePayload();
    const current = objectToShape(vinylObjects()[0], { includeEditorMeta: true });
    assert(recovered.shapes[0].data[0] === current.data[0], "Background flush lost pending work");
    return { continuousFirstWriteMs: writes[0].time - start, continuousWrites, retryPassed: true, backgroundFlushPassed: true };
  } finally { window.fetch = originalFetch; await clearAutosave(); }
})
