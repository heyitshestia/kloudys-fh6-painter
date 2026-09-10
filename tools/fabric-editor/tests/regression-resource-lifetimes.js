async page => {
  const first = await page.evaluate(async () => {
    const shapes = Array.from({ length: 300 }, (_, i) => ({ type: 1048777, type_word: 201, resource_family: "Gradient_Shapes", resource_index: 1, color: [100, 160, 220, 255], data: [(i % 20) * 30, Math.floor(i / 20) * 30, .2, .2, 0, 0, 0] }));
    const assert = (v, message) => { if (!v) throw new Error(message); };
    await loadPayload({ shapes });
    const retired = vinylObjects().slice();
    const source = retired[0]._originalElement;
    const sourceSize = [source.width, source.height];
    const keys = retired.map(o => o.cacheKey);
    await loadPayload({ shapes });
    assert(retired.every(o => !o._element), "Discarded Fabric images retain instance pixels");
    assert(keys.every(key => !fabric.filterBackend?.textureCache?.[key] && !fabric.filterBackend?.textureCache?.[`${key}_filtered`]), "Discarded images retain filter textures");
    assert(source.width === sourceSize[0] && source.height === sourceSize[1], "Cleanup resized shared resource pixels");
    const image = document.createElement("canvas"); image.width = image.height = 256;
    image.getContext("2d").fillRect(0, 0, 256, 256);
    await loadOverlayImageFromUrl(image.toDataURL(), "lifetime-reference.png");
    hybridRenderNow();
    assert(hybridRenderer.overlay.source, "Reference texture not exercised");
    removeOverlay();
    assert(!hybridRenderer.overlay.source && !hybridRenderer.overlay.texture && !overlaySampler && !overlayImage, "Removed reference still has an owner");
    await loadOverlayImageFromUrl(image.toDataURL(), "replacement-reference.png");
    assert(hybridRenderNow() && hybridRenderer.overlay.source, "Texture was not recreated");
    const current = overlayImage;
    let rejected = false;
    const oversizedSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><!--' + 'x'.repeat(21 * 1024 * 1024) + '--></svg>';
    try { await loadOverlayImageFromUrl(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(oversizedSvg)}`, "oversized-reference.svg"); } catch (_) { rejected = true; }
    assert(rejected && overlayImage === current, "Over-budget reference replaced existing work");
    image.width = image.height = 1;
    const gl = hybridRenderer.gl;
    const loss = gl.getExtension("WEBGL_lose_context");
    assert(loss, "Context loss extension unavailable");
    window.__lifetimeLoss = loss;
    beginHybridRender("context loss regression");
    loss.loseContext();
    return { retiredImages: keys.length, sharedPixelsPreserved: true, referenceReleased: true, oversizedRejected: true };
  });
  await page.waitForFunction(() => hybridDisabledReason === "WebGL context lost");
  await page.evaluate(() => {
    if (hybridRenderActive || hybridRenderNow() || canvas.lowerCanvasEl.style.visibility === "hidden") throw new Error("Lost context did not restore Fabric fallback");
    canvas.renderAll();
    window.__lifetimeLoss.restoreContext();
  });
  await page.waitForFunction(() => hybridRenderer && !hybridRenderer.gl.isContextLost());
  const restored = await page.evaluate(() => {
    if (!hybridRenderNow() || hybridRenderer.gl.getError() !== 0) throw new Error("Restored context failed to redraw");
    const pixels = new Uint8Array(4);
    hybridRenderer.gl.readPixels(100, 100, 1, 1, hybridRenderer.gl.RGBA, hybridRenderer.gl.UNSIGNED_BYTE, pixels);
    if (pixels[3] !== 255) throw new Error("Restored renderer is blank");
    removeOverlay();
    return { contextRestored: true, layers: vinylObjects().length };
  });
  return { ...first, ...restored };
}
