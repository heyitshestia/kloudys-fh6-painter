"use strict";

let currentReference = null;
let databasePromise = null;
const REFERENCE_KEY = "editor_recovery_reference";
const EMPTY_REFERENCE_BYTES = new Blob(['{"data_url":null,"svg_text":null}']).size;

function failure(message, code = "storage_failed") {
  return Object.assign(new Error(message), { code });
}

function openDatabase() {
  if (databasePromise) return databasePromise;
  databasePromise = new Promise((resolve, reject) => {
    const request = indexedDB.open("kfps-editor-recovery-v2", 1);
    let settled = false;
    const fail = error => { if (!settled) { settled = true; reject(error); } };
    const timer = setTimeout(() => fail(failure("Browser recovery storage timed out.")), 5000);
    request.onupgradeneeded = () => {
      request.result.createObjectStore("checkpoints");
      request.result.createObjectStore("references");
    };
    request.onerror = () => { clearTimeout(timer); fail(request.error); };
    request.onblocked = () => { clearTimeout(timer); fail(failure("Browser recovery storage is busy.")); };
    request.onsuccess = () => {
      clearTimeout(timer);
      const db = request.result;
      if (settled) { db.close(); return; }
      settled = true;
      db.onversionchange = () => { db.close(); databasePromise = null; };
      resolve(db);
    };
  }).catch(error => { databasePromise = null; throw error; });
  return databasePromise;
}

async function browserWrite(payload, reference) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(["checkpoints", "references"], "readwrite", { durability: "strict" });
    const checkpoints = transaction.objectStore("checkpoints");
    const references = transaction.objectStore("references");
    let applied = true;
    transaction.oncomplete = () => resolve(applied);
    transaction.onabort = transaction.onerror = () => reject(transaction.error || failure("Browser recovery write failed."));
    const read = checkpoints.get("current");
    read.onsuccess = () => {
      const previous = read.result;
      if (previous && previous.recovery_revision >= payload.recovery_revision) {
        applied = previous.recovery_revision === payload.recovery_revision && JSON.stringify(previous) === JSON.stringify(payload);
        return;
      }
      if (previous) checkpoints.put(previous, "previous");
      checkpoints.put(payload, "current");
      if (reference) {
        const exists = references.getKey(reference.sha256);
        exists.onsuccess = () => { if (exists.result === undefined) references.put(reference.blob, reference.sha256); };
      }
      const keep = new Set([payload[REFERENCE_KEY]?.sha256, previous?.[REFERENCE_KEY]?.sha256].filter(Boolean));
      const keys = references.getAllKeys();
      keys.onsuccess = () => keys.result.forEach(key => { if (!keep.has(key)) references.delete(key); });
    };
  });
}

async function browserRead() {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(["checkpoints", "references"], "readonly");
    const records = [];
    for (const key of ["current", "previous"]) {
      const read = transaction.objectStore("checkpoints").get(key);
      read.onsuccess = () => {
        const payload = read.result;
        if (!payload) return;
        const record = { payload, fallback: key === "previous" };
        records.push(record);
        const identity = payload[REFERENCE_KEY]?.sha256;
        if (identity) {
          const source = transaction.objectStore("references").get(identity);
          source.onsuccess = () => { record.blob = source.result; };
        }
      };
    }
    transaction.oncomplete = () => resolve(records);
    transaction.onabort = transaction.onerror = () => reject(transaction.error || failure("Browser recovery read failed."));
  });
}

async function digest(bytes) {
  const value = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(value), byte => byte.toString(16).padStart(2, "0")).join("");
}

function prepareReference(source) {
  if (!source) return null;
  const state = { source, prepared: null, serverStored: false };
  state.prepared = (async () => {
    const blob = new Blob([JSON.stringify(source)], { type: "application/json" });
    return { blob, size: blob.size, sha256: await digest(await blob.arrayBuffer()) };
  })();
  return state;
}

function portablePayload(payload, reference) {
  const result = { ...payload };
  delete result[REFERENCE_KEY];
  if (reference && result.editor_source_overlay) {
    result.editor_source_overlay = { ...result.editor_source_overlay, ...reference.source };
  }
  return result;
}

async function requestJson(url, options, timeout = 10000) {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(timeout) });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw failure(result.error || `HTTP ${response.status}`, result.code || "http_error");
  return result;
}

async function serverWrite(payload, reference, prepared, config) {
  const headers = { ...config.headers, "Content-Type": "application/json" };
  const upload = async () => {
    const result = await requestJson(`/api/fabric-editor/recovery-reference?sha256=${prepared.sha256}`,
      { method: "POST", headers, body: prepared.blob }, 30000);
    if (result.ok !== true || result.sha256 !== prepared.sha256 || result.size !== prepared.size) {
      throw failure("Recovery reference was not acknowledged.");
    }
    reference.serverStored = true;
  };
  if (reference && !reference.serverStored) await upload();
  const send = () => requestJson("/api/fabric-editor/autosave", { method: "POST", headers, body: JSON.stringify(payload) });
  let result;
  try { result = await send(); }
  catch (error) {
    if (!reference || !String(error.message).includes("Recovery reference is missing")) throw error;
    reference.serverStored = false;
    await upload();
    result = await send();
  }
  if (result.ok !== true || result.applied === false) throw failure("A newer recovery revision is already stored.", "stale_revision");
  return true;
}

async function saveRecovery(payload, reference, config, browserOnly = false) {
  const prepared = reference ? await reference.prepared : null;
  const serialized = JSON.stringify(payload);
  const portableSize = new Blob([serialized]).size + (prepared ? prepared.size - EMPTY_REFERENCE_BYTES : 0);
  if (portableSize > config.maxBytes) throw failure("Recovery exceeds the project storage limit.", "recovery_too_large");
  const checkpoint = prepared ? { ...payload, [REFERENCE_KEY]: { sha256: prepared.sha256, size: prepared.size } } : payload;
  if (browserOnly) return { browserOk: await browserWrite(checkpoint, prepared) };
  const [browser, server] = await Promise.allSettled([
    browserWrite(checkpoint, prepared), serverWrite(checkpoint, reference, prepared, config),
  ]);
  const serverOk = server.status === "fulfilled";
  const browserOk = browser.status === "fulfilled" && browser.value === true;
  const error = serverOk ? "" : String(server.reason?.message || "Recovery write failed.");
  return { serverOk, browserOk, error, retryable: server.reason?.code !== "stale_revision", bytes: portableSize };
}

async function inflateRecord(record, blobLoader) {
  const payload = record.payload;
  if (!payload || !Array.isArray(payload.shapes)) throw failure("Recovery checkpoint has no shapes list.");
  const reference = payload[REFERENCE_KEY];
  if (!reference) return record;
  const blob = await blobLoader(reference);
  if (!blob || blob.size !== reference.size) throw failure("Recovery reference is missing.");
  const bytes = await blob.arrayBuffer();
  if (await digest(bytes) !== reference.sha256) throw failure("Recovery reference checksum does not match.");
  const source = JSON.parse(new TextDecoder().decode(bytes));
  return { ...record, payload: portablePayload(payload, { source }) };
}

async function readRecovery() {
  const candidates = [];
  const errors = [];
  const sources = await Promise.allSettled([
    browserRead(), requestJson("/api/fabric-editor/autosave?compact=1", { cache: "no-store" }, 5000),
  ]);
  let clearedRevision = 0;
  if (sources[0].status === "fulfilled") {
    for (const record of sources[0].value) {
      if (record.payload.action === "clear") clearedRevision = Math.max(clearedRevision, record.payload.recovery_revision || 0);
      candidates.push({ ...record, loadBlob: () => record.blob });
    }
  } else errors.push(sources[0].reason?.message || "Browser recovery read failed.");
  if (sources[1].status === "fulfilled") {
    const data = sources[1].value;
    if (data.payload?.action === "clear") clearedRevision = Math.max(clearedRevision, data.payload.recovery_revision || 0);
    if (data.payload) {
      candidates.unshift({ payload: data.payload, fallback: data.fallback, loadBlob: async reference => {
          const response = await fetch(`/api/fabric-editor/recovery-reference?sha256=${reference.sha256}`,
            { cache: "no-store", signal: AbortSignal.timeout(30000) });
          if (!response.ok) throw failure("Recovery reference is missing.");
          return response.blob();
      } });
    }
    if (data.error) errors.push(data.error);
  } else errors.push(sources[1].reason?.message || "App recovery read failed.");
  const revision = payload => payload.recovery_revision || Math.max(0, Date.parse(payload.saved_at || "") || 0) * 1000;
  const ordered = candidates.filter(record => record.payload.action !== "clear"
    && (!clearedRevision || revision(record.payload) > clearedRevision))
    .sort((left, right) => revision(right.payload) - revision(left.payload));
  for (const record of ordered) {
    try {
      const selected = await inflateRecord(record, record.loadBlob);
      return { payload: selected.payload, fallback: Boolean(selected.fallback), clearedRevision, error: errors.join("; ") };
    } catch (error) { errors.push(error.message); }
  }
  return { payload: null, fallback: false, clearedRevision, error: errors.join("; ") };
}

async function execute(message, reference) {
  const { operation, payload, config } = message;
  if (operation === "recovery") return saveRecovery(payload, reference, config);
  if (operation === "browserRecovery") return saveRecovery(payload, reference, config, true);
  if (operation === "readRecovery") return readRecovery();
  if (operation === "parseFile") return JSON.parse(await message.file.text());
  if (operation === "parseText") return JSON.parse(message.text);
  if (operation === "fetchJSON") {
    const response = await fetch(message.url, { cache: "no-store", signal: AbortSignal.timeout(30000) });
    const data = await response.json();
    if (!response.ok) throw failure(data.error || `HTTP ${response.status}`, "http_error");
    return data;
  }
  if (operation === "referenceImage") {
    const source = reference?.source;
    const url = message.imageUrl || source?.data_url;
    if (new Blob([String(source?.svg_text || url)]).size > message.maxReferenceBytes) {
      throw failure("Reference exceeds its storage budget.", "reference_too_large");
    }
    if (!String(url).startsWith("data:image/")) throw failure("Reference image data is invalid.");
    return (await fetch(url)).blob();
  }
  if (operation === "saveProject") {
    const body = new Blob([JSON.stringify({ name: message.name, payload: portablePayload(payload, reference), overwrite: message.overwrite })],
      { type: "application/json" });
    if (body.size > config.maxBytes) throw failure("Project exceeds the save limit.", "project_too_large");
    return requestJson("/api/fabric-editor/save-project", { method: "POST", headers: config.headers, body }, 30000);
  }
  throw failure("Unknown persistence operation.");
}

self.onmessage = event => {
  const message = event.data;
  if (Object.prototype.hasOwnProperty.call(message, "reference")) currentReference = prepareReference(message.reference);
  // Capture immutable reference ownership before another queued request changes it.
  const reference = message.payload?.editor_source_overlay ? currentReference : null;
  execute(message, reference).then(
    value => self.postMessage({ id: message.id, value }),
    error => self.postMessage({ id: message.id, error: String(error.message || error), code: error.code || "storage_failed" }),
  );
};
