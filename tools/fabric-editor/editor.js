/* global fabric */
"use strict";

const FH6_BOUNDS = { left: -1000, top: -1000, width: 2000, height: 2000 };
const LEGACY_RECTANGLE_TYPES = new Set([1, 2]);
const LEGACY_ELLIPSE_TYPES = new Set([8, 16]);
const RECTANGLE_DIVISOR = 127.0;
const ELLIPSE_DIVISOR = 63.0;

const VINYL_TYPE_BASES = {
  Primitives: 1048677,
  Community_Vinyls_1: 1050677,
  Community_Vinyls_2: 1050777,
  Community_Vinyls_3: 1050877,
  Community_Vinyls_4: 1050977,
  Gradient_Shapes: 1048777,
  Stripes: 1048877,
  Tears: 1048977,
  Racing_Icons: 1049077,
  Flames: 1049177,
  Paint_Splats: 1049277,
  Tribal: 1049377,
  Nature: 1049477,
  Upper_Letters_1: 1050477,
  Lower_Letters_1: 1050577,
  Upper_Letters_2: 1049877,
  Lower_Letters_2: 1049977,
  Upper_Letters_3: 1050077,
  Lower_Letters_3: 1050177,
  Upper_Letters_4: 1050277,
  Lower_Letters_4: 1050377,
  Upper_Letters_5: 1051077,
  Lower_Letters_5: 1051177,
  Upper_Letters_6: 1051277,
  Lower_Letters_6: 1051377,
  Upper_Letters_7: 1051477,
  Lower_Letters_7: 1051577,
  Upper_Letters_8: 1051677,
  Lower_Letters_8: 1051777,
  Upper_Letters_9: 1051877,
  Lower_Letters_9: 1051977,
  Upper_Letters_10: 1052077,
  Lower_Letters_10: 1052177,
  Upper_Letters_11: 1052277,
  Lower_Letters_11: 1052377,
};

const FAMILY_ORDER = Object.keys(VINYL_TYPE_BASES);
const resourceCache = new Map();
let canvas;
let isPanning = false;
let lastPan = null;
let loadedName = "untitled";
let overlayImage = null;
let history = [];
let historyIndex = -1;
let historyLocked = false;
let showFavoritesOnly = false;
let favorites = new Set(JSON.parse(localStorage.getItem("kloudyFabricFavorites") || "[]"));
let shapeNames = { families: {} };
let rememberedColor = [255, 255, 255, 255];
let overlaySampler = null;
let liveOverlayColorFrame = null;

try {
  const savedColor = JSON.parse(localStorage.getItem("kloudyFabricLastColor") || "null");
  if (Array.isArray(savedColor) && savedColor.length >= 3) rememberedColor = savedColor;
} catch (_err) {
  rememberedColor = [255, 255, 255, 255];
}

function $(id) {
  return document.getElementById(id);
}

function setStatus(message) {
  $("status").textContent = message;
}

function setBusy(message) {
  $("busyText").textContent = message;
  $("busyBanner").hidden = false;
  setStatus(message);
}

function clearBusy(message = null) {
  $("busyBanner").hidden = true;
  if (message) setStatus(message);
}

function showError(prefix, err) {
  const message = err && err.stack ? err.stack : (err && err.message ? err.message : String(err));
  console.error(prefix, err);
  clearBusy(`${prefix}: ${message.split("\n")[0]}`);
  alert(`${prefix}\n\n${message}`);
}

function nextFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

function colorToHex(color) {
  const c = normalizeColor(color);
  return `#${c[0].toString(16).padStart(2, "0")}${c[1].toString(16).padStart(2, "0")}${c[2].toString(16).padStart(2, "0")}`;
}

function normalizeColor(color) {
  const out = Array.isArray(color) ? color.slice(0, 4) : [255, 255, 255, 255];
  while (out.length < 4) out.push(255);
  return out.map((v) => Math.max(0, Math.min(255, Math.round(Number(v) || 0))));
}

function hexToRgb(hex, alpha) {
  const clean = hex.replace("#", "");
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
    Math.max(0, Math.min(255, Math.round(Number(alpha) || 255))),
  ];
}

function typeCodeToResource(typeCode) {
  for (const [family, base] of Object.entries(VINYL_TYPE_BASES)) {
    const index = typeCode - base + 1;
    if (index >= 1 && index <= 80) return { family, index, typeCode };
  }
  return null;
}

function resourceToTypeCode(family, index) {
  return VINYL_TYPE_BASES[family] + index - 1;
}

async function loadResourcePath(typeCode) {
  if (resourceCache.has(typeCode)) return resourceCache.get(typeCode);
  const resolved = typeCodeToResource(typeCode);
  if (!resolved) throw new Error(`Unsupported FH6 type code: ${typeCode}`);
  const url = `/tools/fabric-editor/Resources/Vinyls/${resolved.family}/${resolved.index}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Missing shape resource: ${url}`);
  const payload = await response.json();
  const vertices = payload.Vertices || [];
  const indices = payload.Indices || [];
  const chunks = [];
  for (let i = 0; i + 2 < indices.length; i += 3) {
    const p0 = vertices[indices[i]];
    const p1 = vertices[indices[i + 1]];
    const p2 = vertices[indices[i + 2]];
    if (!p0 || !p1 || !p2) continue;
    chunks.push(`M ${fmt(p0.X)} ${fmt(p0.Y)} L ${fmt(p1.X)} ${fmt(p1.Y)} L ${fmt(p2.X)} ${fmt(p2.Y)} Z`);
  }
  const d = chunks.join(" ");
  resourceCache.set(typeCode, d);
  return d;
}

function fmt(value) {
  return String(Math.round(Number(value) * 1000000) / 1000000);
}

function legacyBoundsForShape(shape) {
  const data = Array.isArray(shape.data) ? shape.data : [];
  if (data.length < 4) return null;
  const x = Number(data[0]) || 0;
  const y = Number(data[1]) || 0;
  const w = Math.abs(Number(data[2]) || 1);
  const h = Math.abs(Number(data[3]) || 1);
  return { minX: x - w / 2, maxX: x + w / 2, minY: y - h / 2, maxY: y + h / 2 };
}

function computeLegacyOffset(shapes) {
  let bounds = null;
  for (const shape of shapes) {
    const type = Number(shape.type);
    if (!LEGACY_RECTANGLE_TYPES.has(type) && !LEGACY_ELLIPSE_TYPES.has(type)) continue;
    const b = legacyBoundsForShape(shape);
    if (!b) continue;
    bounds = bounds ? {
      minX: Math.min(bounds.minX, b.minX),
      maxX: Math.max(bounds.maxX, b.maxX),
      minY: Math.min(bounds.minY, b.minY),
      maxY: Math.max(bounds.maxY, b.maxY),
    } : b;
  }
  if (!bounds) return { x: 0, y: 0 };
  return { x: (bounds.minX + bounds.maxX) / 2, y: (bounds.minY + bounds.maxY) / 2 };
}

function legacyToFh6Shape(shape, legacyOffset = { x: 0, y: 0 }) {
  const type = Number(shape.type);
  const data = Array.isArray(shape.data) ? shape.data : [];
  if (data.length < 4) throw new Error("Legacy shape requires at least x,y,w,h data.");
  const x = Number(data[0]) || 0;
  const y = Number(data[1]) || 0;
  const w = Number(data[2]) || 1;
  const h = Number(data[3]) || 1;
  const rot = Number(data[4]) || 0;
  const isRect = LEGACY_RECTANGLE_TYPES.has(type);
  const divisor = isRect ? RECTANGLE_DIVISOR : ELLIPSE_DIVISOR;
  const fullCode = isRect ? 1048677 : 1048678;
  return {
    type: fullCode,
    type_word: fullCode & 0xffff,
    data: [
      x - legacyOffset.x,
      -(y - legacyOffset.y),
      w / divisor,
      h / divisor,
      isRect && type === 1 ? 0 : (360 - rot) % 360,
      Number(data[5]) || 0,
      shape.mask ? 1 : 0,
    ],
    color: normalizeColor(shape.color),
    mask: Boolean(shape.mask),
    score: Number(shape.score) || 0,
    source_format: "legacy_geometry",
    legacy_type: type,
    legacy_divisor: divisor,
    legacy_offset: [legacyOffset.x, legacyOffset.y],
  };
}

function normalizeInputShape(shape, index, legacyOffset = { x: 0, y: 0 }) {
  const color = normalizeColor(shape.color);
  if (index === 0 && Number(shape.type) === 1 && color[3] <= 0) return null;
  if (color[3] <= 0) return null;
  const type = Number(shape.type);
  if (LEGACY_RECTANGLE_TYPES.has(type) || LEGACY_ELLIPSE_TYPES.has(type)) {
    return legacyToFh6Shape(shape, legacyOffset);
  }
  if (type > 1000000) {
    const data = Array.isArray(shape.data) ? shape.data.slice() : [];
    while (data.length < 7) data.push(0);
    return {
      ...shape,
      type,
      type_word: Number(shape.type_word ?? (type & 0xffff)),
      data,
      color,
      mask: Boolean(shape.mask || data[6]),
      score: Number(shape.score) || 0,
    };
  }
  return null;
}

async function makeFabricObject(shape, name = null) {
  const typeCode = Number(shape.type);
  const d = await loadResourcePath(typeCode);
  const color = normalizeColor(shape.color);
  const data = shape.data || [0, 0, 1, 1, 0, 0, 0];
  const object = new fabric.Path(d, {
    originX: "center",
    originY: "center",
    left: Number(data[0]) || 0,
    top: -(Number(data[1]) || 0),
    scaleX: Number(data[2]) || 1,
    scaleY: Number(data[3]) || 1,
    angle: -(Number(data[4]) || 0),
    skewX: radiansToDegrees(Math.atan(Number(data[5]) || 0)),
    fill: colorToHex(color),
    opacity: color[3] / 255,
    stroke: shape.mask ? "#ff5572" : null,
    strokeWidth: shape.mask ? 3 : 0,
    objectCaching: false,
    noScaleCache: true,
    perPixelTargetFind: true,
    targetFindTolerance: 3,
    hoverCursor: "pointer",
    moveCursor: "move",
  });
  object.kloudy = {
    name: name || typeLabel(typeCode),
    type: typeCode,
    type_word: Number(shape.type_word ?? (typeCode & 0xffff)),
    source_format: shape.source_format || "fh6_typecode",
    legacy_type: shape.legacy_type ?? null,
    legacy_divisor: shape.legacy_divisor ?? null,
    legacy_offset: Array.isArray(shape.legacy_offset) ? shape.legacy_offset.slice(0, 2) : null,
    score: Number(shape.score) || 0,
    extra: data.slice(5),
    mask: Boolean(shape.mask || data[6]),
  };
  return object;
}

function radiansToDegrees(value) {
  return value * 180 / Math.PI;
}

function degreesToTan(value) {
  return Math.tan(value * Math.PI / 180);
}

function typeLabel(typeCode) {
  const resolved = typeCodeToResource(typeCode);
  if (!resolved) return `Unknown ${typeCode}`;
  return shapeDisplayName(resolved.family, resolved.index);
}

function shapeDisplayName(family, index) {
  return shapeNames?.families?.[family]?.[String(index)] || `${family.replaceAll("_", " ")} #${index}`;
}

function shapeSearchText(family, index, typeCode) {
  return [
    family,
    family.replaceAll("_", " "),
    index,
    typeCode,
    `#${index}`,
    shapeDisplayName(family, index),
  ].join(" ").toLowerCase();
}

function shapeCountForFamily(family) {
  const named = shapeNames?.families?.[family];
  if (named && Object.keys(named).length) {
    return Math.max(...Object.keys(named).map((key) => Number(key) || 0));
  }
  if (family.startsWith("Upper_Letters_")) return 26;
  if (family.startsWith("Lower_Letters_")) return 39;
  return 40;
}

async function loadShapeNames() {
  try {
    const response = await fetch("/tools/fabric-editor/shape-names.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    shapeNames = await response.json();
    renderShapeGrid();
  } catch (err) {
    console.warn("Shape names unavailable.", err);
  }
}

function rememberColor(color) {
  rememberedColor = normalizeColor(color);
  localStorage.setItem("kloudyFabricLastColor", JSON.stringify(rememberedColor));
}

function objectToShape(object) {
  const meta = object.kloudy || {};
  const color = hexToRgb(object.fill || "#ffffff", (object.opacity ?? 1) * 255);
  const extra = Array.isArray(meta.extra) ? meta.extra.slice() : [];
  const skew = degreesToTan(object.skewX || 0);
  const data = [
    round(object.left || 0),
    round(-(object.top || 0)),
    round(object.scaleX || 1),
    round(object.scaleY || 1),
    round((-(object.angle || 0) + 360) % 360),
    round(skew),
    meta.mask ? 1 : 0,
  ];
  if (extra.length > 2) data.push(...extra.slice(2));
  return {
    type: Number(meta.type),
    type_word: Number(meta.type_word ?? (Number(meta.type) & 0xffff)),
    data,
    color,
    mask: Boolean(meta.mask),
    score: Number(meta.score) || 0,
    source_format: meta.source_format || "fh6_typecode",
    legacy_type: meta.legacy_type ?? null,
    legacy_divisor: meta.legacy_divisor ?? null,
    legacy_offset: Array.isArray(meta.legacy_offset) ? meta.legacy_offset.slice(0, 2) : null,
  };
}

function objectToLegacyShape(object) {
  const meta = object.kloudy || {};
  const typeCode = Number(meta.type);
  const color = hexToRgb(object.fill || "#ffffff", (object.opacity ?? 1) * 255);
  const isRect = typeCode === 1048677;
  const isEllipse = typeCode === 1048678;
  if (!isRect && !isEllipse) {
    throw new Error(`${meta.name || typeLabel(typeCode)} is not supported by the normal importer export.`);
  }
  const offset = Array.isArray(meta.legacy_offset) ? meta.legacy_offset : [0, 0];
  const divisor = Number(meta.legacy_divisor) || (isRect ? RECTANGLE_DIVISOR : ELLIPSE_DIVISOR);
  const fh6Rotation = (-(object.angle || 0) + 360) % 360;
  const rotation = round((360 - fh6Rotation) % 360);
  return {
    type: isRect && Math.abs(rotation) < 0.000001 ? 1 : (isRect ? 2 : 16),
    data: [
      round((object.left || 0) + (Number(offset[0]) || 0)),
      round((object.top || 0) + (Number(offset[1]) || 0)),
      round((object.scaleX || 1) * divisor),
      round((object.scaleY || 1) * divisor),
      rotation,
      round(degreesToTan(object.skewX || 0)),
    ],
    color,
    score: Number(meta.score) || 0,
    mask: Boolean(meta.mask),
  };
}

function snapshotShapes() {
  return vinylObjects().map(objectToShape);
}

async function restoreShapes(shapes) {
  historyLocked = true;
  clearVinylObjects();
  for (const shape of shapes) {
    const object = await makeFabricObject(shape);
    canvas.add(object);
  }
  bringGuidesToBack();
  historyLocked = false;
  refreshLayers();
  canvas.requestRenderAll();
}

function pushHistory(reason = "change") {
  if (historyLocked) return;
  const snapshot = JSON.stringify(snapshotShapes());
  if (history[historyIndex] === snapshot) return;
  history = history.slice(0, historyIndex + 1);
  history.push(snapshot);
  if (history.length > 80) history.shift();
  historyIndex = history.length - 1;
  localStorage.setItem("kloudyFabricAutosave", JSON.stringify({
    name: loadedName,
    created: new Date().toISOString(),
    shapes: JSON.parse(snapshot),
  }));
  setStatus(`Saved ${reason}. Autosave updated.`);
}

async function undo() {
  if (historyIndex <= 0) return;
  historyIndex--;
  await restoreShapes(JSON.parse(history[historyIndex]));
  setStatus("Undo.");
}

async function redo() {
  if (historyIndex >= history.length - 1) return;
  historyIndex++;
  await restoreShapes(JSON.parse(history[historyIndex]));
  setStatus("Redo.");
}

function round(value) {
  const n = Math.round(Number(value) * 1000000) / 1000000;
  return Math.abs(n - Math.round(n)) < 0.000001 ? Math.round(n) : n;
}

function initCanvas() {
  canvas = new fabric.Canvas("canvas", {
    preserveObjectStacking: true,
    selection: true,
    selectionKey: "shiftKey",
    fireRightClick: true,
    stopContextMenu: true,
    backgroundColor: "#0b0d12",
    perPixelTargetFind: true,
    targetFindTolerance: 3,
    defaultCursor: "default",
    hoverCursor: "default",
    moveCursor: "move",
    freeDrawingCursor: "default",
  });
  resizeCanvas();
  window.addEventListener("resize", resizeCanvas);
  resetView();
  canvas.on("selection:created", updateSelectionPanel);
  canvas.on("selection:updated", updateSelectionPanel);
  canvas.on("selection:cleared", updateSelectionPanel);
  canvas.on("object:modified", () => {
    if ($("autoOverlayColor")?.checked) {
      selectedVinylObjects().forEach((obj) => applyOverlayColorToObject(obj, { remember: true, silent: true }));
    }
    updateSelectionPanel();
    refreshLayers();
    pushHistory("object edit");
  });
  ["object:moving", "object:scaling", "object:rotating", "object:skewing"].forEach((eventName) => {
    canvas.on(eventName, (event) => scheduleLiveOverlayColor(event.target));
  });
  canvas.on("mouse:wheel", (opt) => {
    const delta = opt.e.deltaY;
    let zoom = canvas.getZoom();
    zoom *= 0.999 ** delta;
    zoom = Math.min(Math.max(zoom, 0.04), 8);
    canvas.zoomToPoint({ x: opt.e.offsetX, y: opt.e.offsetY }, zoom);
    opt.e.preventDefault();
    opt.e.stopPropagation();
  });
  canvas.on("mouse:down", (opt) => {
    if (opt.e.button === 1 || opt.e.button === 2) {
      isPanning = true;
      lastPan = { x: opt.e.clientX, y: opt.e.clientY };
      canvas.selection = false;
    }
  });
  canvas.on("mouse:move", (opt) => {
    if (!isPanning || !lastPan) return;
    const vpt = canvas.viewportTransform;
    vpt[4] += opt.e.clientX - lastPan.x;
    vpt[5] += opt.e.clientY - lastPan.y;
    canvas.requestRenderAll();
    lastPan = { x: opt.e.clientX, y: opt.e.clientY };
  });
  canvas.on("mouse:up", () => {
    isPanning = false;
    canvas.selection = true;
  });
}

function resizeCanvas() {
  const wrap = document.querySelector(".canvasWrap");
  const rect = wrap.getBoundingClientRect();
  canvas.setDimensions({ width: rect.width, height: rect.height });
  canvas.requestRenderAll();
}

/*
 * The FH6 bounds guides are intentionally disabled. They were visual-only and
 * never exported, but the editor is easier to use as an open canvas.
 */
function drawBounds() {
  const group = [];
  const bounds = new fabric.Rect({
    left: FH6_BOUNDS.left,
    top: FH6_BOUNDS.top,
    width: FH6_BOUNDS.width,
    height: FH6_BOUNDS.height,
    fill: "rgba(255,255,255,0.035)",
    stroke: "#6ee7ff",
    strokeWidth: 3,
    selectable: false,
    evented: false,
    excludeFromExport: true,
  });
  const xAxis = new fabric.Line([-1200, 0, 1200, 0], {
    stroke: "rgba(255,255,255,0.22)",
    strokeWidth: 1,
    selectable: false,
    evented: false,
    excludeFromExport: true,
  });
  const yAxis = new fabric.Line([0, -1200, 0, 1200], {
    stroke: "rgba(255,255,255,0.22)",
    strokeWidth: 1,
    selectable: false,
    evented: false,
    excludeFromExport: true,
  });
  group.push(bounds, xAxis, yAxis);
  group.forEach((item) => {
    item.kloudyGuide = true;
    canvas.add(item);
    item.sendToBack();
  });
}

function resetView() {
  const zoom = Math.min(canvas.width / 2400, canvas.height / 2400);
  canvas.setViewportTransform([zoom, 0, 0, zoom, canvas.width / 2, canvas.height / 2]);
  canvas.requestRenderAll();
}

function fitDesignView() {
  const objects = vinylObjects();
  if (!objects.length) {
    resetView();
    return;
  }
  let bounds = null;
  objects.forEach((obj) => {
    obj.setCoords();
    const rect = obj.getBoundingRect(true, true);
    bounds = bounds ? {
      left: Math.min(bounds.left, rect.left),
      top: Math.min(bounds.top, rect.top),
      right: Math.max(bounds.right, rect.left + rect.width),
      bottom: Math.max(bounds.bottom, rect.top + rect.height),
    } : {
      left: rect.left,
      top: rect.top,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
    };
  });
  const width = Math.max(1, bounds.right - bounds.left);
  const height = Math.max(1, bounds.bottom - bounds.top);
  const centerX = bounds.left + width / 2;
  const centerY = bounds.top + height / 2;
  const zoom = Math.min(canvas.width / (width * 1.18), canvas.height / (height * 1.18), 2.5);
  canvas.setViewportTransform([
    zoom, 0, 0, zoom,
    canvas.width / 2 - centerX * zoom,
    canvas.height / 2 - centerY * zoom,
  ]);
  canvas.requestRenderAll();
}

async function loadJsonFile(file) {
  setBusy(`Loading JSON: ${file.name}`);
  await nextFrame();
  const text = await file.text();
  const payload = JSON.parse(text);
  loadedName = file.name.replace(/\.json$/i, "");
  await loadPayload(payload);
}

async function loadPayload(payload) {
  const shapes = Array.isArray(payload.shapes) ? payload.shapes : null;
  if (!shapes) throw new Error("JSON must contain a shapes list.");
  clearVinylObjects();
  const hasLegacyGeometry = shapes.some((shape) => LEGACY_RECTANGLE_TYPES.has(Number(shape.type)) || LEGACY_ELLIPSE_TYPES.has(Number(shape.type)));
  const legacyOffset = hasLegacyGeometry ? computeLegacyOffset(shapes) : { x: 0, y: 0 };
  const normalized = shapes.map((shape, index) => normalizeInputShape(shape, index, legacyOffset)).filter(Boolean);
  setBusy(`Building ${normalized.length} editable layer(s)...`);
  await nextFrame();
  let loaded = 0;
  let failed = 0;
  for (const shape of normalized) {
    try {
      const object = await makeFabricObject(shape);
      canvas.add(object);
      loaded++;
    } catch (err) {
      failed++;
      console.warn(err);
    }
    if (loaded % 100 === 0) {
      setBusy(`Building layers: ${loaded}/${normalized.length}`);
      await nextFrame();
    }
  }
  bringGuidesToBack();
  refreshLayers();
  fitDesignView();
  pushHistory("import");
  clearBusy(`Loaded ${loaded}/${normalized.length} editable FH6 layer(s).${failed ? ` Failed: ${failed}.` : ""}`);
}

function clearVinylObjects() {
  canvas.getObjects().filter((obj) => !obj.kloudyGuide).forEach((obj) => canvas.remove(obj));
}

function vinylObjects() {
  return canvas.getObjects().filter((obj) => obj.kloudy && !obj.kloudyGuide);
}

function selectedVinylObjects() {
  const active = canvas.getActiveObject();
  if (!active) return [];
  if ((active.type === "activeSelection" || active.type === "activeselection") && Array.isArray(active._objects)) {
    return active._objects.filter((obj) => obj.kloudy && !obj.kloudyGuide);
  }
  return active.kloudy && !active.kloudyGuide ? [active] : [];
}

function bringGuidesToBack() {
  canvas.getObjects().filter((obj) => obj.kloudyGuide).forEach((obj) => obj.sendToBack());
}

function refreshLayers() {
  const list = $("layers");
  list.innerHTML = "";
  const objects = vinylObjects();
  const activeSet = new Set(selectedVinylObjects());
  $("layerInfo").textContent = activeSet.size > 1
    ? `${activeSet.size} selected / ${objects.length} editable layer(s). Drag selection to move together.`
    : `${objects.length} editable layer(s). Export writes bottom-to-top order.`;
  objects.slice().reverse().forEach((obj, reverseIndex) => {
    const actualIndex = objects.length - reverseIndex;
    const li = document.createElement("li");
    li.textContent = `${actualIndex}. ${obj.kloudy?.name || typeLabel(obj.kloudy?.type || 0)}`;
    if (activeSet.has(obj)) li.classList.add("active");
    li.addEventListener("click", () => {
      canvas.setActiveObject(obj);
      canvas.requestRenderAll();
      updateSelectionPanel();
      refreshLayers();
    });
    list.appendChild(li);
  });
}

function updateSelectionPanel() {
  const selected = selectedVinylObjects();
  const enabled = selected.length === 1;
  ["colorPicker", "opacitySlider", "xInput", "yInput", "sxInput", "syInput", "rotInput", "skewInput", "maskInput", "applyFields"].forEach((id) => {
    $(id).disabled = !enabled;
  });
  if (!enabled) {
    if (selected.length > 1) {
      $("layerInfo").textContent = `${selected.length} layer(s) selected. Drag the selection box to move them together.`;
    }
    refreshLayers();
    return;
  }
  const obj = selected[0];
  $("colorPicker").value = obj.fill || "#ffffff";
  $("opacitySlider").value = Math.round((obj.opacity ?? 1) * 255);
  $("xInput").value = round(obj.left || 0);
  $("yInput").value = round(-(obj.top || 0));
  $("sxInput").value = round(obj.scaleX || 1);
  $("syInput").value = round(obj.scaleY || 1);
  $("rotInput").value = round((-(obj.angle || 0) + 360) % 360);
  $("skewInput").value = round(degreesToTan(obj.skewX || 0));
  $("maskInput").checked = Boolean(obj.kloudy.mask);
  refreshLayers();
}

function applySelectionFields() {
  const obj = selectedVinylObjects()[0];
  if (!obj || !obj.kloudy) return;
  const color = hexToRgb($("colorPicker").value, $("opacitySlider").value);
  rememberColor(color);
  obj.set({
    fill: colorToHex(color),
    opacity: color[3] / 255,
    left: Number($("xInput").value) || 0,
    top: -(Number($("yInput").value) || 0),
    scaleX: Number($("sxInput").value) || 1,
    scaleY: Number($("syInput").value) || 1,
    angle: -(Number($("rotInput").value) || 0),
    skewX: radiansToDegrees(Math.atan(Number($("skewInput").value) || 0)),
  });
  obj.kloudy.mask = $("maskInput").checked;
  obj.set({ stroke: obj.kloudy.mask ? "#ff5572" : null, strokeWidth: obj.kloudy.mask ? 3 : 0 });
  obj.setCoords();
  canvas.requestRenderAll();
  updateSelectionPanel();
  pushHistory("field edit");
}

function downloadText(filename, text) {
  const blob = new Blob([text], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportJson() {
  const shapes = vinylObjects().map(objectToShape);
  downloadText(`${loadedName || "vinyl"}.fabric-export.json`, JSON.stringify({ shapes }, null, 2));
  setStatus(`Exported ${shapes.length} FH6 JSON layer(s).`);
}

function exportLegacyJson() {
  try {
    const shapes = vinylObjects().map(objectToLegacyShape);
    downloadText(`${loadedName || "vinyl"}.normal-import.json`, JSON.stringify({ shapes }, null, 2));
    setStatus(`Exported ${shapes.length} normal-import compatible rectangle/ellipse layer(s).`);
  } catch (err) {
    showError("Normal import export failed", new Error(
      `${err.message}\n\nNormal importer export only supports generated rectangle/ellipse layers. ` +
      "Use Export FH6 JSON and the handmade importer for full shape-library designs."
    ));
  }
}

function saveProject() {
  const payload = {
    format: "kloudy_fabric_editor_project_v1",
    name: loadedName,
    shapes: vinylObjects().map(objectToShape),
  };
  downloadText(`${loadedName || "vinyl"}.fabric-project.json`, JSON.stringify(payload, null, 2));
}

async function loadProjectFile(file) {
  setBusy(`Loading project: ${file.name}`);
  await nextFrame();
  const payload = JSON.parse(await file.text());
  loadedName = file.name.replace(/\.json$/i, "");
  await loadPayload({ shapes: payload.shapes || [] });
}

function viewportCenterPoint() {
  const inverse = fabric.util.invertTransform(canvas.viewportTransform);
  return fabric.util.transformPoint(new fabric.Point(canvas.width / 2, canvas.height / 2), inverse);
}

function placeNewObjectInViewport(object) {
  const center = viewportCenterPoint();
  object.set({ left: center.x, top: center.y });
  object.setCoords();
  const zoom = Math.max(canvas.getZoom() || 1, 0.001);
  const currentMax = Math.max(object.getScaledWidth(), object.getScaledHeight(), 1);
  const targetScreenSize = Math.max(56, Math.min(128, Math.min(canvas.width, canvas.height) * 0.14));
  const scaleFactor = targetScreenSize / (currentMax * zoom);
  object.set({
    scaleX: (object.scaleX || 1) * scaleFactor,
    scaleY: (object.scaleY || 1) * scaleFactor,
  });
  object.setCoords();
}

async function addShape(family, index) {
  const typeCode = resourceToTypeCode(family, index);
  const shape = {
    type: typeCode,
    type_word: typeCode & 0xffff,
    data: [0, 0, 1, 1, 0, 0, 0],
    color: rememberedColor,
    mask: false,
    score: 0,
  };
  const object = await makeFabricObject(shape);
  placeNewObjectInViewport(object);
  if ($("autoOverlayColor")?.checked) applyOverlayColorToObject(object, { remember: true, silent: true });
  canvas.add(object);
  canvas.setActiveObject(object);
  bringGuidesToBack();
  canvas.requestRenderAll();
  refreshLayers();
  updateSelectionPanel();
  pushHistory("add shape");
}

function buildShapeLibrary() {
  const select = $("shapeFamily");
  FAMILY_ORDER.forEach((family) => {
    const option = document.createElement("option");
    option.value = family;
    option.textContent = family.replaceAll("_", " ");
    select.appendChild(option);
  });
  select.value = "Primitives";
  select.addEventListener("change", renderShapeGrid);
  $("shapeSearch").addEventListener("input", renderShapeGrid);
  loadShapeNames();
  renderShapeGrid();
}

function renderShapeGrid() {
  const selectedFamily = $("shapeFamily").value;
  const query = $("shapeSearch").value.trim().toLowerCase();
  const grid = $("shapeGrid");
  grid.innerHTML = "";
  const families = (query || showFavoritesOnly) ? FAMILY_ORDER : [selectedFamily];
  for (const family of families) for (let index = 1; index <= shapeCountForFamily(family); index++) {
    const typeCode = resourceToTypeCode(family, index);
    const favKey = `${family}:${index}`;
    const isFavorite = favorites.has(favKey);
    if (showFavoritesOnly && !isFavorite) continue;
    const name = shapeDisplayName(family, index);
    if (query && !shapeSearchText(family, index, typeCode).includes(query)) continue;
    const tile = document.createElement("div");
    tile.className = `shapeTile${isFavorite ? " favorite" : ""}`;
    tile.tabIndex = 0;
    tile.title = `${name}\n${family.replaceAll("_", " ")} #${index}\nType ${typeCode}`;
    tile.innerHTML = `
      <button class="favButton" type="button" title="${isFavorite ? "Remove favorite" : "Add favorite"}">${isFavorite ? "x" : "+"}</button>
      <img alt="" src="/tools/fabric-editor/Resources/Vinyls/${family}/${index}.png">
      <span class="shapeName">${escapeHtml(name)}</span>
      <span class="shapeMeta">${family.replaceAll("_", " ")} #${index}</span>
    `;
    tile.addEventListener("click", () => addShape(family, index));
    tile.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        addShape(family, index);
      }
    });
    tile.querySelector(".favButton").addEventListener("click", (event) => {
      event.stopPropagation();
      toggleFavorite(family, index);
    });
    grid.appendChild(tile);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toggleFavorite(family, index) {
  const key = `${family}:${index}`;
  if (favorites.has(key)) favorites.delete(key);
  else favorites.add(key);
  localStorage.setItem("kloudyFabricFavorites", JSON.stringify([...favorites]));
  renderShapeGrid();
}

function duplicateSelected() {
  const objects = selectedVinylObjects();
  if (!objects.length) return;
  Promise.all(objects.map((obj) => new Promise((resolve) => {
    obj.clone((clone) => {
      clone.set({ left: (obj.left || 0) + 30, top: (obj.top || 0) + 30 });
      clone.kloudy = JSON.parse(JSON.stringify(obj.kloudy));
      clone.perPixelTargetFind = $("pixelSelect").checked;
      clone.targetFindTolerance = $("pixelSelect").checked ? 3 : 0;
      clone.hoverCursor = "pointer";
      clone.moveCursor = "move";
      canvas.add(clone);
      resolve(clone);
    });
  }))).then((clones) => {
    if (clones.length === 1) {
      canvas.setActiveObject(clones[0]);
    } else {
      canvas.setActiveObject(new fabric.ActiveSelection(clones, { canvas }));
    }
    refreshLayers();
    canvas.requestRenderAll();
    pushHistory("duplicate");
  });
}

function deleteSelected() {
  const objects = selectedVinylObjects();
  if (!objects.length) return;
  objects.forEach((obj) => canvas.remove(obj));
  canvas.discardActiveObject();
  canvas.requestRenderAll();
  refreshLayers();
  pushHistory("delete");
}

function moveSelected(direction) {
  const objects = selectedVinylObjects();
  if (!objects.length) return;
  objects.forEach((obj) => {
    if (direction > 0) obj.bringForward();
    else obj.sendBackwards();
  });
  bringGuidesToBack();
  refreshLayers();
  pushHistory("layer order");
}

function nudgeSelected(dx, dy) {
  const objects = selectedVinylObjects();
  if (!objects.length) return;
  objects.forEach((obj) => {
    obj.set({ left: (obj.left || 0) + dx, top: (obj.top || 0) + dy });
    obj.setCoords();
  });
  canvas.requestRenderAll();
  updateSelectionPanel();
  pushHistory("nudge");
}

function setPixelSelection(enabled) {
  if ($("pixelSelect")) $("pixelSelect").checked = enabled;
  if ($("boxVisibleOnly")) $("boxVisibleOnly").checked = enabled;
  canvas.perPixelTargetFind = enabled;
  canvas.targetFindTolerance = enabled ? 3 : 0;
  vinylObjects().forEach((obj) => {
    obj.perPixelTargetFind = enabled;
    obj.targetFindTolerance = enabled ? 3 : 0;
  });
}

function rebuildOverlaySampler(img) {
  const width = img.naturalWidth || img.width || 1;
  const height = img.naturalHeight || img.height || 1;
  const sampleCanvas = document.createElement("canvas");
  sampleCanvas.width = width;
  sampleCanvas.height = height;
  const ctx = sampleCanvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, width, height);
  overlaySampler = {
    width,
    height,
    data: ctx.getImageData(0, 0, width, height).data,
  };
}

function canvasPointToOverlayPixel(x, y) {
  if (!overlayImage || !overlaySampler) return null;
  const inverse = fabric.util.invertTransform(overlayImage.calcTransformMatrix());
  const local = fabric.util.transformPoint(new fabric.Point(x, y), inverse);
  const px = Math.round(local.x + (overlayImage.width || overlaySampler.width) / 2);
  const py = Math.round(local.y + (overlayImage.height || overlaySampler.height) / 2);
  if (px < 0 || py < 0 || px >= overlaySampler.width || py >= overlaySampler.height) return null;
  return { x: px, y: py };
}

function dominantOverlayColorForObject(obj) {
  if (!obj || !overlaySampler) return null;
  obj.setCoords();
  const rect = obj.getBoundingRect(true, true);
  const stepsX = Math.max(5, Math.min(27, Math.ceil(rect.width / 65)));
  const stepsY = Math.max(5, Math.min(27, Math.ceil(rect.height / 65)));
  const bins = new Map();
  for (let iy = 0; iy < stepsY; iy++) {
    const y = rect.top + rect.height * ((iy + 0.5) / stepsY);
    for (let ix = 0; ix < stepsX; ix++) {
      const x = rect.left + rect.width * ((ix + 0.5) / stepsX);
      const pixel = canvasPointToOverlayPixel(x, y);
      if (!pixel) continue;
      const pos = (pixel.y * overlaySampler.width + pixel.x) * 4;
      const r = overlaySampler.data[pos];
      const g = overlaySampler.data[pos + 1];
      const b = overlaySampler.data[pos + 2];
      const a = overlaySampler.data[pos + 3];
      if (a < 24) continue;
      const key = `${r >> 4},${g >> 4},${b >> 4}`;
      const bin = bins.get(key) || { count: 0, r: 0, g: 0, b: 0, a: 0 };
      bin.count++;
      bin.r += r;
      bin.g += g;
      bin.b += b;
      bin.a += a;
      bins.set(key, bin);
    }
  }
  let best = null;
  for (const bin of bins.values()) {
    if (!best || bin.count > best.count || (bin.count === best.count && bin.a > best.a)) best = bin;
  }
  if (!best) return null;
  return [
    Math.round(best.r / best.count),
    Math.round(best.g / best.count),
    Math.round(best.b / best.count),
    255,
  ];
}

function applyOverlayColorToObject(obj, options = {}) {
  const color = dominantOverlayColorForObject(obj);
  if (!color) {
    if (!options.silent) setStatus("No overlay color found under the selected layer.");
    return false;
  }
  const alpha = Math.round((obj.opacity ?? 1) * 255);
  const applied = [color[0], color[1], color[2], alpha];
  obj.set({ fill: colorToHex(applied), opacity: alpha / 255 });
  if (options.remember) rememberColor(applied);
  if (canvas.getActiveObject() === obj) {
    $("colorPicker").value = colorToHex(applied);
    $("opacitySlider").value = alpha;
  }
  obj.setCoords();
  return true;
}

function scheduleLiveOverlayColor(target) {
  if (!$("autoOverlayColor")?.checked || !overlaySampler) return;
  if (liveOverlayColorFrame) return;
  liveOverlayColorFrame = requestAnimationFrame(() => {
    liveOverlayColorFrame = null;
    const objects = selectedVinylObjects();
    const targets = objects.length ? objects : (target?.kloudy ? [target] : []);
    let changed = false;
    targets.forEach((obj) => {
      if (applyOverlayColorToObject(obj, { remember: true, silent: true })) changed = true;
    });
    if (changed) {
      updateSelectionPanel();
      canvas.requestRenderAll();
    }
  });
}

function sampleOverlayColorForSelected() {
  const objects = selectedVinylObjects();
  if (!objects.length) {
    setStatus("Select one or more layers before sampling overlay color.");
    return;
  }
  let changed = 0;
  objects.forEach((obj) => {
    if (applyOverlayColorToObject(obj, { remember: true, silent: true })) changed++;
  });
  canvas.requestRenderAll();
  updateSelectionPanel();
  if (changed) {
    pushHistory("overlay color sample");
    setStatus(`Sampled overlay color for ${changed} selected layer(s).`);
  } else {
    setStatus("No overlay pixels found under the selected layer(s).");
  }
}

function addOverlayFile(file) {
  const reader = new FileReader();
  reader.onload = () => {
    const img = new Image();
    img.onload = () => {
      if (overlayImage) canvas.remove(overlayImage);
      rebuildOverlaySampler(img);
      overlayImage = new fabric.Image(img, {
        originX: "center",
        originY: "center",
        left: 0,
        top: 0,
        opacity: Number($("overlayOpacity").value) / 100,
        selectable: false,
        evented: false,
        excludeFromExport: true,
      });
      overlayImage.kloudyOverlay = true;
      const fit = 1800 / Math.max(img.width, img.height);
      overlayImage.set({ scaleX: fit, scaleY: fit });
      canvas.add(overlayImage);
      overlayImage.sendToBack();
      bringGuidesToBack();
      canvas.requestRenderAll();
      setStatus(`Overlay loaded: ${file.name}`);
    };
    img.src = reader.result;
  };
  reader.readAsDataURL(file);
}

function updateOverlay() {
  if (!overlayImage) return;
  const base = 1800 / Math.max(overlayImage.width || 1, overlayImage.height || 1);
  const factor = Number($("overlayScale").value) / 100;
  overlayImage.set({
    opacity: Number($("overlayOpacity").value) / 100,
    scaleX: base * factor,
    scaleY: base * factor,
  });
  canvas.requestRenderAll();
}

function toggleOverlay() {
  if (!overlayImage) return;
  overlayImage.visible = !overlayImage.visible;
  canvas.requestRenderAll();
}

function removeOverlay() {
  if (!overlayImage) return;
  canvas.remove(overlayImage);
  overlayImage = null;
  overlaySampler = null;
  canvas.requestRenderAll();
}

function bindUi() {
  $("jsonInput").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(`Selected JSON: ${file.name}`);
    loadJsonFile(file)
      .catch((err) => showError("JSON import failed", err))
      .finally(() => { event.target.value = ""; });
  });
  $("projectInput").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(`Selected project: ${file.name}`);
    loadProjectFile(file)
      .catch((err) => showError("Project load failed", err))
      .finally(() => { event.target.value = ""; });
  });
  $("exportJson").addEventListener("click", exportJson);
  $("exportLegacyJson").addEventListener("click", exportLegacyJson);
  $("saveProject").addEventListener("click", saveProject);
  $("fitView").addEventListener("click", fitDesignView);
  $("resetView").addEventListener("click", resetView);
  $("undoBtn").addEventListener("click", undo);
  $("redoBtn").addEventListener("click", redo);
  $("helpBtn").addEventListener("click", () => $("helpDialog").showModal());
  $("closeHelp").addEventListener("click", () => $("helpDialog").close());
  $("applyFields").addEventListener("click", applySelectionFields);
  $("deleteLayer").addEventListener("click", deleteSelected);
  $("duplicateLayer").addEventListener("click", duplicateSelected);
  $("bringForward").addEventListener("click", () => moveSelected(1));
  $("sendBackward").addEventListener("click", () => moveSelected(-1));
  $("colorPicker").addEventListener("input", applySelectionFields);
  $("opacitySlider").addEventListener("input", applySelectionFields);
  $("pixelSelect").addEventListener("change", () => setPixelSelection($("pixelSelect").checked));
  $("boxVisibleOnly").addEventListener("change", () => setPixelSelection($("boxVisibleOnly").checked));
  $("overlayInput").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (file) addOverlayFile(file);
  });
  $("overlayOpacity").addEventListener("input", updateOverlay);
  $("overlayScale").addEventListener("input", updateOverlay);
  $("sampleOverlayColor").addEventListener("click", sampleOverlayColorForSelected);
  $("toggleOverlay").addEventListener("click", toggleOverlay);
  $("removeOverlay").addEventListener("click", removeOverlay);
  $("showFavorites").addEventListener("click", () => {
    showFavoritesOnly = true;
    renderShapeGrid();
  });
  $("showAllShapes").addEventListener("click", () => {
    showFavoritesOnly = false;
    renderShapeGrid();
  });
  document.addEventListener("keydown", (event) => {
    if (event.target && ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      deleteSelected();
      return;
    }
    if (event.ctrlKey && event.key.toLowerCase() === "z") {
      event.preventDefault();
      undo();
      return;
    }
    if (event.ctrlKey && event.key.toLowerCase() === "y") {
      event.preventDefault();
      redo();
      return;
    }
    if (event.ctrlKey && event.key.toLowerCase() === "d") {
      event.preventDefault();
      duplicateSelected();
      return;
    }
    const step = (Number($("nudgeStep").value) || 1) * (event.shiftKey ? 10 : 1);
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      nudgeSelected(-step, 0);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      nudgeSelected(step, 0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      nudgeSelected(0, -step);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      nudgeSelected(0, step);
    } else if (event.key === "]") {
      event.preventDefault();
      moveSelected(1);
    } else if (event.key === "[") {
      event.preventDefault();
      moveSelected(-1);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initCanvas();
  buildShapeLibrary();
  bindUi();
  updateSelectionPanel();
  const autosave = localStorage.getItem("kloudyFabricAutosave");
  if (autosave && window.confirm("Recover the last autosaved Fabric editor project?")) {
    try {
      const payload = JSON.parse(autosave);
      loadedName = payload.name || "autosave";
      loadPayload({ shapes: payload.shapes || [] }).catch((err) => setStatus(`Autosave recovery failed: ${err.message}`));
    } catch (err) {
      setStatus(`Autosave recovery failed: ${err.message}`);
    }
  }
});
