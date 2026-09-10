(function installPersistence(global) {
  "use strict";

  class EditorPersistence {
    constructor(config) {
      this.config = config;
      this.worker = null;
      this.pending = new Map();
      this.nextId = 0;
      this.lastReference = undefined;
    }

    reset(error) {
      this.worker?.terminate();
      this.worker = null;
      this.lastReference = undefined;
      for (const request of this.pending.values()) {
        clearTimeout(request.timer);
        request.reject(error);
      }
      this.pending.clear();
    }

    start() {
      if (this.worker) return;
      const worker = new Worker("/tools/fabric-editor/editor-persistence-worker.js?v=1");
      this.worker = worker;
      worker.onmessage = event => {
        const message = event.data;
        const pending = this.pending.get(message.id);
        if (!pending) return;
        clearTimeout(pending.timer);
        this.pending.delete(message.id);
        if (message.error) pending.reject(Object.assign(new Error(message.error), { code: message.code }));
        else pending.resolve(message.value);
      };
      worker.onerror = event => {
        event.preventDefault();
        this.reset(Object.assign(new Error("The background save worker stopped. Recovery will retry."), { code: "worker_failed" }));
      };
      worker.onmessageerror = () => this.reset(new Error("The background save worker returned an unreadable response."));
    }

    request(operation, data = {}) {
      try { this.start(); }
      catch (error) { return Promise.reject(error); }
      if (this.pending.size >= 8) return Promise.reject(new Error("Background storage is busy. Try again in a moment."));
      const message = { ...data, operation, id: ++this.nextId, config: this.config };
      if (data.payload) {
        message.payload = { ...data.payload };
        const overlay = data.payload.editor_source_overlay;
        const reference = overlay ? { data_url: overlay.data_url || null, svg_text: overlay.svg_text || null } : null;
        if (this.lastReference === undefined || reference?.data_url !== this.lastReference?.data_url
          || reference?.svg_text !== this.lastReference?.svg_text) {
          message.reference = reference;
        }
        // Equal text can still be a newly parsed string after reopening. Retain
        // the current source, not an additional old copy of a large reference.
        this.lastReference = reference;
        if (overlay) message.payload.editor_source_overlay = { ...overlay, data_url: null, svg_text: null };
      }
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => this.reset(Object.assign(new Error("Background storage timed out. Recovery will retry."), { code: "worker_timeout" })), 45000);
        this.pending.set(message.id, { resolve, reject, timer });
        try { this.worker.postMessage(message); }
        catch (error) { this.reset(error); }
      });
    }
  }

  global.KfpsEditorPersistence = { create: config => new EditorPersistence(config) };
})(window);
