async page => {
  const results = [];
  const probe = async (name, fn) => {
    await page.evaluate(async () => {
      document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
      documentDirty = false;
      await startBlankCanvas();
    });
    try { results.push({ name, ...(await fn()) }); }
    catch (error) { results.push({ name, probeError: String(error) }); }
  };

  await probe('new-during-document-build', () => page.evaluate(async () => {
    const original = makeFabricObject;
    let unblock, entered;
    const gate = new Promise(resolve => { unblock = resolve; });
    const started = new Promise(resolve => { entered = resolve; });
    makeFabricObject = async shape => { entered(); await gate; return original(shape); };
    try {
      const loading = loadPayload({ shapes: [{ type: 1048677, data: [0, 0, 1, 1, 0, 0, 0], color: [100, 150, 200, 255] }] });
      await started;
      documentDirty = false;
      await startBlankCanvas();
      unblock();
      await loading;
      return { preserved: vinylObjects().length === 0 && currentProjectName === null, layers: vinylObjects().length };
    } finally { unblock(); makeFabricObject = original; }
  }));

  await probe('history-resource-failure', () => page.evaluate(async () => {
    await loadPayload({ shapes: [0, 1].map(i => ({ type: 1048677 + i, data: [i * 100, 0, 1, 1, 0, 0, 0], color: [90, 140, 210, 255] })) });
    canvas.setActiveObject(vinylObjects()[0]);
    nudgeSelected(50, 0); flushPendingNudgeHistory();
    canvas.setActiveObject(vinylObjects()[1]); deleteSelected();
    const before = JSON.stringify(snapshotShapes()), index = historyIndex;
    const original = makeFabricObject;
    makeFabricObject = async () => { throw new Error('Injected unavailable shape resource'); };
    let error = null;
    try { await jumpToHistory(protectedHistoryIndex); } catch (failure) { error = failure.message; }
    finally { makeFabricObject = original; }
    return { preserved: before === JSON.stringify(snapshotShapes()) && historyIndex === index && !historyLocked,
      exactShapes: before === JSON.stringify(snapshotShapes()), historyIndex, previousIndex: index, error };
  }));

  await probe('text-replacement-resource-failure', () => page.evaluate(async () => {
    document.getElementById('textVinylInput').value = 'ABC';
    document.getElementById('textVinylClearPrevious').checked = true;
    await generateTextVinylShapes();
    const before = JSON.stringify(snapshotShapes()), index = historyIndex;
    const original = makeFabricObject;
    makeFabricObject = async () => { throw new Error('Injected unavailable font resource'); };
    try {
      document.getElementById('textVinylInput').value = 'DEF';
      await generateTextVinylShapes();
    } finally { makeFabricObject = original; }
    return { preserved: before === JSON.stringify(snapshotShapes()) && historyIndex === index && !historyLocked,
      layers: vinylObjects().length, historyIndex, previousIndex: index };
  }));

  await probe('replacement-confirmation-dialog', () => page.evaluate(async () => {
    const resolved = [];
    requestConfirmation('First', 'First confirmation').then(value => resolved.push(['first', value]));
    requestConfirmation('Second', 'Second confirmation').then(value => resolved.push(['second', value]));
    await nextFrame(); await nextFrame();
    const before = resolved.slice();
    document.getElementById('confirmationDialogConfirm').click();
    await Promise.resolve();
    return { preserved: before.length === 1 && resolved[1]?.[1] === true, before, resolved };
  }));

  await probe('zero-alpha-color-change', () => page.evaluate(async () => {
    await loadPayload({ shapes: [0, 1].map(i => ({ type: 1048677, data: [i * 100, 0, 1, 1, 0, 0, 0], color: [90, 140, 210, 0] })) });
    selectAllLayers(); updateSelectionPanel(); openColorDialog();
    const picker = document.getElementById('dialogColorPicker');
    picker.value = '#ef9060'; picker.dispatchEvent(new Event('change', { bubbles: true }));
    document.getElementById('closeColorDialog').click();
    const colors = snapshotShapes().map(shape => shape.color);
    return { preserved: colors.every(color => color[3] === 0), colors };
  }));

  await probe('reference-install-failure', () => page.evaluate(async () => {
    const source = document.createElement('canvas'); source.width = source.height = 32;
    const ctx = source.getContext('2d'); ctx.fillStyle = '#aabbcc'; ctx.fillRect(0, 0, 32, 32);
    const url = source.toDataURL();
    await loadOverlayImageFromUrl(url, 'Original reference.png');
    const before = JSON.stringify(sourceOverlayProjectState());
    const original = canvas.add;
    let injected = false;
    canvas.add = function(...objects) {
      if (!injected && objects.some(object => object.kloudyOverlay)) { injected = true; throw new Error('Injected overlay installation failure'); }
      return original.apply(this, objects);
    };
    let error;
    try { await loadOverlayImageFromUrl(url, 'Replacement reference.png'); }
    catch (failure) { error = failure.message; }
    finally { canvas.add = original; }
    return { preserved: before === JSON.stringify(sourceOverlayProjectState()) && overlayImage?.canvas === canvas, injected, error };
  }));

  await probe('svg-refresh-after-removal', () => page.evaluate(async () => {
    const text = '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><g id="color_1"><rect width="32" height="32" fill="#aabbcc"/></g></svg>';
    layeredOverlayState = parseLayeredSvg(text, 'Layered.svg');
    await loadOverlayImageFromUrl(layeredSvgDataUrl(), 'Layered.svg');
    const OriginalImage = window.Image;
    let delivered, held;
    const ready = new Promise(resolve => { delivered = resolve; });
    window.Image = function(...args) {
      const image = new OriginalImage(...args);
      image.addEventListener('load', event => {
        event.stopImmediatePropagation(); held = () => image.onload?.(); delivered();
      });
      return image;
    };
    let error = null;
    try {
      refreshLayeredOverlayImage();
      await ready;
      removeOverlay();
      try { held(); } catch (failure) { error = failure.message; }
    } finally { window.Image = OriginalImage; }
    return { preserved: !error && !overlayImage && !overlaySourceState && !overlaySampler, error };
  }));
  const failures = results.filter(result => result.preserved !== true);
  if (failures.length) throw new Error(JSON.stringify(failures));
  return { results };
}
