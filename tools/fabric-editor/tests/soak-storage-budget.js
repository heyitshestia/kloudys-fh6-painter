async (page, options) => {
  page.setDefaultTimeout(180000);
  const cdp = await page.context().newCDPSession(page);
  await page.evaluate(async () => {
    await clearAutosave();
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => ({
      type: 1048677, color: [80, 150, 220, 255], data: [i % 60 * 22 - 660, Math.floor(i / 60) * 22 - 550, .1, .1, 0, 0, 0],
    })) });
    currentProjectName = "Storage soak";
    fitDesignView();
    window.storageSoak = { maxGap: 0, tasks: 0, maxTask: 0 };
    let previous = performance.now();
    requestAnimationFrame(function sample(now) { storageSoak.maxGap = Math.max(storageSoak.maxGap, now - previous); previous = now; requestAnimationFrame(sample); });
    new PerformanceObserver(list => { for (const entry of list.getEntries()) { storageSoak.tasks++; storageSoak.maxTask = Math.max(storageSoak.maxTask, entry.duration); } }).observe({ type: "longtask" });
  });
  const checkpoints = [];
  const started = Date.now();
  for (let cycle = 0; cycle < 6; cycle++) {
    const size = cycle % 2 ? 49 : 35;
    await page.locator("#overlayInput").setInputFiles(`${options.fixtures}/reference-${size}.png`);
    await page.waitForFunction(size => overlaySourceState?.fileName === `reference-${size}.png`, size);
    let edits = 0;
    do {
      await page.evaluate(async cycle => {
        selectObjects(vinylObjects().slice(cycle * 30, cycle * 30 + 30), "storage soak");
        for (let i = 0; i < 40; i++) { nudgeSelected(i % 2 ? 1 : -1, 0); await new Promise(resolve => setTimeout(resolve, 60)); }
        nudgeSelected(1, 0); flushPendingNudgeHistory(); await flushPendingAutosave();
        if (!autosaveStatus.serverOk) throw new Error("Soak recovery failed: " + autosaveStatus.error);
      }, cycle);
      edits += 41;
    } while (Date.now() - started < (cycle + 1) * 60000);
    const state = await page.evaluate(async () => {
      const recovery = await readAutosavePayload();
      if (JSON.stringify(recovery.shapes) !== JSON.stringify(snapshotShapes()) || recovery.editor_source_overlay.data_url !== overlaySourceState.dataUrl) throw new Error("Soak recovery readback changed data");
      await saveProject();
      if (documentDirty) throw new Error("Soak project save failed");
      return { ...storageSoak, layers: vinylObjects().length, history: history.length, pixels: overlaySampler.width * overlaySampler.height, browserFallback: autosaveStatus.browserOk };
    });
    // Freeze one retained-state sample after each replacement/edit/save cycle.
    await cdp.send("HeapProfiler.collectGarbage");
    checkpoints.push({ cycle, size, edits, seconds: (Date.now() - started) / 1000, ...state, heap: await cdp.send("Runtime.getHeapUsage") });
    console.log(JSON.stringify({ checkpoint: checkpoints.at(-1) }));
  }
  await page.screenshot({ path: "storage-soak.png" });
  await page.evaluate(async () => { removeOverlay(); clearVinylObjects(); resetHistory(); refreshLayers(); await clearAutosave(); documentDirty = false; });
  await cdp.send("HeapProfiler.collectGarbage");
  const cleared = await cdp.send("Runtime.getHeapUsage");
  await cdp.detach();
  return { checkpoints, cleared, seconds: (Date.now() - started) / 1000 };
}
