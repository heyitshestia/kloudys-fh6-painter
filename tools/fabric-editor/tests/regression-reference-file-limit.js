async (page, options) => {
  page.setDefaultTimeout(180000);
  const cdp = await page.context().newCDPSession(page);
  const setFile = async name => {
    const { root } = await cdp.send('DOM.getDocument');
    const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#overlayInput' });
    await cdp.send('DOM.setFileInputFiles', { nodeId, files: [`${options.fixtures}/${name}`] });
  };
  try {
    await page.evaluate(async () => {
      await loadPayload({ shapes: [{ type: 1048677, color: [25, 160, 200, 255], data: [0, 0, 1, 1, 0, 0, 0] }] });
      currentProjectName = 'Real reference boundary';
    });
    await setFile('reference-99.png');
    await page.waitForFunction(() => overlaySourceState?.fileName === 'reference-99.png');
    const accepted = await page.evaluate(async () => {
      const bytes = new Blob([overlaySourceState.dataUrl]).size;
      if (bytes <= 98 * 1024 * 1024 || bytes >= EDITOR_REFERENCE_MAX_BYTES) throw new Error('Fixture does not exercise the new near-limit reference');
      if (overlaySampler.width * overlaySampler.height !== 48000000) throw new Error('Decoded reference lost resolution');
      if (JSON.stringify([...readOverlayPixel(17, 23)].slice(0, 3)) !== '[18,52,86]') throw new Error('Original marker pixel changed');
      await saveProject();
      if (documentDirty) throw new Error('Accepted reference could not be saved');
      await flushPendingAutosave();
      if (!autosaveStatus.serverOk || !autosaveStatus.browserOk) throw new Error('Accepted reference lacks both recovery copies');
      const file = await readEditorDocument(`${PROJECT_FILE_API}?id=Real%20reference%20boundary.fabric-project.json`);
      if (file.payload.editor_source_overlay.data_url !== overlaySourceState.dataUrl) throw new Error('Project reference bytes changed');
      await loadProjectPayload(file.payload, 'Real reference boundary');
      window.referenceLimitExpected = { image: overlayImage, url: overlaySourceState.dataUrl, state: JSON.stringify(snapshotShapes()) };
      return { bytes, pixels: overlaySampler.width * overlaySampler.height };
    });
    await setFile('reference-101.png');
    await page.waitForFunction(() => $('status').textContent.includes(KfpsI18n.t('Reference exceeds the {0} MiB storage budget. Use a smaller image.', EDITOR_REFERENCE_MAX_BYTES / (1024 * 1024))));
    const rejected = await page.evaluate(async () => {
      if (overlayImage !== referenceLimitExpected.image || overlaySourceState.dataUrl !== referenceLimitExpected.url
        || JSON.stringify(snapshotShapes()) !== referenceLimitExpected.state) throw new Error('Rejected file altered existing artwork/reference');
      const saved = await readEditorDocument(`${PROJECT_FILE_API}?id=Real%20reference%20boundary.fabric-project.json`);
      if (saved.payload.editor_source_overlay.data_url !== referenceLimitExpected.url) throw new Error('Rejected reference overwrote project');
      delete window.referenceLimitExpected;
      return { previousImagePreserved: true, previousProjectPreserved: true };
    });
    await page.screenshot({ path: 'reference-limit-preserved.png' });
    await page.evaluate(async () => { removeOverlay(); clearVinylObjects(); resetHistory(); refreshLayers(); await clearAutosave(); documentDirty = false; });
    return { accepted, rejected, nativeFileInput: true };
  } finally { await cdp.detach(); }
}
