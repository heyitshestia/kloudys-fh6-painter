async (page, options) => {
  page.setDefaultTimeout(180000);
  const cdp = await page.context().newCDPSession(page);
  const checks = [];
  const referenceFile = options.referenceFile || "reference-49.png";
  await page.evaluate(async () => {
    if (typeof clearVinylObjects !== "function" || typeof resetHistory !== "function" || typeof refreshLayers !== "function") throw new Error("Storage test cleanup helpers unavailable");
    await clearAutosave();
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => ({
      type: 1048677, color: [90, 160, 220, 255],
      data: [i % 60 * 20 - 600, Math.floor(i / 60) * 20 - 500, .1, .1, 0, 0, 0],
    })) });
    window.capacityDigest = async value => Array.from(new Uint8Array(await crypto.subtle.digest(
      "SHA-256", new TextEncoder().encode(JSON.stringify(value))
    )), byte => byte.toString(16).padStart(2, "0")).join("");
    window.capacitySetSize = target => {
      const objects = vinylObjects();
      objects.forEach(object => { object.kloudy.name = ""; });
      const base = new Blob([JSON.stringify(editableProjectPayload("Capacity boundary"))]).size;
      const length = Math.floor((target - base) / objects.length);
      objects.forEach((object, i) => { object.kloudy.name = String(i).padStart(4, "0") + "x".repeat(length - 4); });
      pushHistory("capacity boundary test");
      return new Blob([JSON.stringify(editableProjectPayload("Capacity boundary"))]).size;
    };
  });
  const { root } = await cdp.send("DOM.getDocument");
  const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector: "#overlayInput" });
  await cdp.send("DOM.setFileInputFiles", { nodeId, files: [`${options.fixtures}/${referenceFile}`] });
  await page.waitForFunction(name => overlaySourceState?.fileName === name, referenceFile);
  const saved = await page.evaluate(async () => {
    const bytes = capacitySetSize(EDITOR_PROJECT_MAX_BYTES - 0.5 * 1024 * 1024);
    currentProjectName = "Capacity boundary";
    const before = performance.now();
    await saveProject();
    if (documentDirty) throw new Error("Near-limit save failed");
    const saveMs = performance.now() - before;
    const expected = await capacityDigest({ shapes: snapshotShapes(), reference: overlaySourceState.dataUrl });
    const response = await fetch(`${PROJECT_FILE_API}?id=Capacity%20boundary.fabric-project.json`);
    const { payload } = await response.json();
    if (await capacityDigest({ shapes: payload.shapes, reference: payload.editor_source_overlay.data_url }) !== expected) throw new Error("Near-limit saved file changed data");
    await loadProjectPayload(payload, "Capacity boundary");
    if (await capacityDigest({ shapes: snapshotShapes(), reference: overlaySourceState.dataUrl }) !== expected) throw new Error("Near-limit reopened project changed data");
    selectObjects(vinylObjects().slice(0, 1), "capacity recovery");
    nudgeSelected(1, 0); flushPendingNudgeHistory();
    const recoveryStart = performance.now();
    await flushPendingAutosave();
    if (!autosaveStatus.serverOk || !autosaveStatus.browserOk) throw new Error("Near-limit recovery did not acknowledge both storage copies");
    const recoveryMs = performance.now() - recoveryStart;
    const recovered = await readAutosavePayload();
    const recoveryHash = await capacityDigest({ shapes: snapshotShapes(), reference: overlaySourceState.dataUrl });
    if (await capacityDigest({ shapes: recovered.shapes, reference: recovered.editor_source_overlay.data_url }) !== recoveryHash) throw new Error("Near-limit recovery changed data");
    return { bytes, saveMs, recoveryMs, expected, recoveryHash };
  });
  checks.push({ nearLimit: saved });
  const rejected = await page.evaluate(async saved => {
    const bytes = capacitySetSize(EDITOR_PROJECT_MAX_BYTES + 0.5 * 1024 * 1024);
    await saveProject();
    if (!documentDirty) throw new Error("Rejected save marked document clean");
    await flushPendingAutosave();
    if (autosaveStatus.state !== "failed" || autosaveRetryTimer) throw new Error("Over-limit recovery claimed success or kept retrying");
    const project = await (await fetch(`${PROJECT_FILE_API}?id=Capacity%20boundary.fabric-project.json`)).json();
    const recovery = await readAutosavePayload();
    if (await capacityDigest({ shapes: project.payload.shapes, reference: project.payload.editor_source_overlay.data_url }) !== saved.expected) throw new Error("Rejected save changed previous file");
    if (await capacityDigest({ shapes: recovery.shapes, reference: recovery.editor_source_overlay.data_url }) !== saved.recoveryHash) throw new Error("Rejected recovery changed previous file");
    await recoverAutosavePayload(recovery);
    document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
    return { bytes, priorProjectPreserved: true, priorRecoveryPreserved: true };
  }, saved);
  checks.push({ overLimit: rejected });
  await page.evaluate(() => flushPendingAutosave());
  const worker = page.workers().find(item => item.url().includes("editor-persistence-worker"));
  await worker.evaluate(() => {
    self.originalCapacityFetch = fetch;
    let failures = 0;
    self.fetch = (...args) => {
      if (args[0] === "/api/fabric-editor/autosave" && args[1]?.method === "POST" && failures++ === 0) return Promise.resolve(new Response("unavailable", { status: 503 }));
      return originalCapacityFetch(...args);
    };
  });
  const retry = await page.evaluate(async () => {
      selectObjects(vinylObjects().slice(0, 1), "capacity retry");
      nudgeSelected(1, 0); flushPendingNudgeHistory(); await flushPendingAutosave();
      if (autosaveStatus.serverOk || !autosaveStatus.browserOk || !documentDirty) throw new Error("Large recovery did not identify the browser-only fallback");
      const start = performance.now();
      while (!autosaveStatus.serverOk && performance.now() - start < 25000) await new Promise(resolve => setTimeout(resolve, 200));
      if (!autosaveStatus.serverOk) throw new Error("Large recovery automatic retry failed");
      const recovered = await readAutosavePayload();
      const hash = await capacityDigest({ shapes: recovered.shapes, reference: recovered.editor_source_overlay.data_url });
      if (hash !== await capacityDigest({ shapes: snapshotShapes(), reference: overlaySourceState.dataUrl })) throw new Error("Retried recovery lost latest edit");
      return { automaticRetry: true, hash };
  });
  await worker.evaluate(() => { self.fetch = originalCapacityFetch; delete self.originalCapacityFetch; });
  checks.push(retry);
  await page.evaluate(() => { documentDirty = false; });
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  const restart = await page.evaluate(async () => {
    document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
    const recovered = await readAutosavePayload();
    await recoverAutosavePayload(recovered);
    const data = { shapes: snapshotShapes(), reference: overlaySourceState.dataUrl };
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(data)))), byte => byte.toString(16).padStart(2, "0")).join("");
    return { hash, count: vinylObjects().length, pixels: overlaySampler.width * overlaySampler.height };
  });
  if (restart.hash !== retry.hash || restart.count !== 3000 || restart.pixels !== (options.expectedPixels || 24000000)) throw new Error("Large recovery after page restart lost artwork or pixels");
  checks.push({ restart });
  await page.screenshot({ path: "near-limit-recovered.png" });
  await cdp.send("HeapProfiler.collectGarbage");
  checks.push({ retained: await cdp.send("Runtime.getHeapUsage") });
  console.log(JSON.stringify({ capacityChecks: checks }));
  await page.evaluate(async () => { removeOverlay(); clearVinylObjects(); resetHistory(); refreshLayers(); await clearAutosave(); documentDirty = false; });
  await cdp.send("HeapProfiler.collectGarbage");
  checks.push({ cleared: await cdp.send("Runtime.getHeapUsage") });
  await cdp.detach();
  return checks;
}
