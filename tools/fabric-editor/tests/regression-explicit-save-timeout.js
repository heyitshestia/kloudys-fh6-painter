async (page) => {
  page.setDefaultTimeout(45000);
  await page.evaluate(async () => {
    document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
    await loadPayload({ shapes: [{ type: 1048677, color: [40, 150, 210, 255], data: [0, 0, 0.5, 0.5, 0, 0, 0] }] });
    await flushPendingAutosave();
  });
  const worker = page.workers().find(item => item.url().includes("editor-persistence-worker"));
  await worker.evaluate(() => {
    self.auditOriginalFetch = fetch;
    self.fetch = (url, options) => url === "/api/fabric-editor/save-project"
      ? new Promise((resolve, reject) => options.signal?.addEventListener("abort", () => reject(options.signal.reason), { once: true }))
      : self.auditOriginalFetch(url, options);
  });
  try {
    await page.locator("#saveProjectAs").click();
    await page.locator("#textPromptInput").fill("Timeout retry");
    const started = Date.now();
    await page.locator("#textPromptInput").press("Enter");
    await page.locator("#messageDialog").waitFor({ state: "visible" });
    const elapsed = Date.now() - started;
    if (elapsed < 29000 || elapsed > 40000) throw new Error(`Unexpected save timeout ${elapsed}`);
    if (!await page.evaluate(() => !projectSaveInProgress && documentDirty && !document.getElementById("saveProjectAs").disabled)) throw new Error("Failed save lost dirty state or left controls disabled");
    await worker.evaluate(() => { self.fetch = self.auditOriginalFetch; });
    await page.locator("#messageDialogClose").click();
    await page.locator("#saveProjectAs").click();
    await page.locator("#textPromptInput").fill("Timeout retry");
    await page.locator("#textPromptInput").press("Enter");
    await page.waitForFunction(() => !projectSaveInProgress && currentProjectName === "Timeout retry");
    const disk = await page.evaluate(async () => {
      const listing = await (await fetch(PROJECT_BROWSER_API)).json();
      const entry = listing.entries.find(item => item.title === "Timeout retry");
      return (await (await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}`)).json()).payload;
    });
    if (disk.shapes.length !== 1) throw new Error("Retry did not save the document to disk");
    return { timeoutMs: elapsed, retrySavedToDisk: true, dirtyStatePreserved: true };
  } finally {
    await worker.evaluate(() => { self.fetch = self.auditOriginalFetch; delete self.auditOriginalFetch; });
  }
}
