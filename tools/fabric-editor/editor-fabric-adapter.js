(function installKfpsFabricAdapter(global) {
  "use strict";

  const runtime = global.fabric;
  if (!runtime) throw new Error("Fabric.js did not load.");

  const version = String(runtime.version || "unknown");
  const major = Number.parseInt(version.split(".")[0], 10);
  if (!Number.isFinite(major) || major < 5 || major > 7) {
    throw new Error(`Unsupported Fabric.js runtime: ${version}`);
  }

  function scenePoint(canvas, event) {
    if (typeof canvas?.getScenePoint === "function") return canvas.getScenePoint(event);
    if (typeof canvas?.getPointer === "function") return canvas.getPointer(event);
    throw new Error("Fabric canvas does not expose a scene-coordinate pointer API.");
  }

  function moveObjectTo(canvas, object, index) {
    if (!canvas || !object) return false;
    if (typeof canvas.moveObjectTo === "function") return canvas.moveObjectTo(object, index);
    if (typeof object.moveTo === "function") {
      object.moveTo(index);
      return true;
    }
    return false;
  }

  function sendObjectToBack(canvas, object) {
    if (!canvas || !object) return false;
    if (typeof canvas.sendObjectToBack === "function") return canvas.sendObjectToBack(object);
    if (typeof object.sendToBack === "function") {
      object.sendToBack();
      return true;
    }
    return false;
  }

  function bringObjectToFront(canvas, object) {
    if (!canvas || !object) return false;
    if (typeof canvas.bringObjectToFront === "function") return canvas.bringObjectToFront(object);
    if (typeof object.bringToFront === "function") {
      object.bringToFront();
      return true;
    }
    return false;
  }

  function replaceObjectStack(canvas, objects) {
    if (!canvas || !Array.isArray(objects)) return false;
    const current = canvas.getObjects();
    if (current.length === objects.length && objects.every((object, index) => current[index] === object)) {
      return false;
    }
    if (objects.some((object) => !object) || new Set(objects).size !== objects.length) {
      throw new Error("Refusing to replace the Fabric stack with missing or duplicate objects.");
    }
    canvas._objects = objects.slice();
    objects.forEach((object) => {
      object.canvas = canvas;
    });
    canvas.requestRenderAll();
    return true;
  }

  function cancelObjectTransform(canvas) {
    const transform = canvas?._currentTransform;
    if (!transform) return null;
    // Do not finalize: that would emit object:modified and record the partial
    // drag while history is restoring an earlier state.
    canvas._currentTransform = null;
    canvas._groupSelector = null;
    if (transform.target) {
      transform.target.isMoving = false;
      transform.target._scaling = false;
      transform.target.__corner = 0;
    }
    return transform;
  }

  // KFPS never imports or serializes SVG through Fabric. Keep that boundary
  // explicit while the supported Fabric migration remains performance-gated.
  function unsupportedSvgOperation() {
    throw new Error("Fabric SVG import and serialization are disabled in the KFPS editor.");
  }
  ["loadSVGFromString", "loadSVGFromURL"].forEach((name) => {
    if (typeof runtime[name] === "function") runtime[name] = unsupportedSvgOperation;
  });
  [runtime.Canvas?.prototype, runtime.StaticCanvas?.prototype].forEach((prototype) => {
    if (prototype && typeof prototype.toSVG === "function") prototype.toSVG = unsupportedSvgOperation;
  });

  let hitSurface = null;
  function visiblePixelAt(canvas, object, point) {
    const bounds = object.getBoundingRect(true, true);
    if (point.x < bounds.left || point.y < bounds.top || point.x > bounds.left + bounds.width || point.y > bounds.top + bounds.height) return false;
    if (!hitSurface) { hitSurface = document.createElement("canvas"); hitSurface.width = hitSurface.height = 3; }
    const context = hitSurface.getContext("2d", { willReadFrequently: true });
    const screen = runtime.util.transformPoint(point, canvas.viewportTransform);
    const previous = { objectCaching: object.objectCaching, globalCompositeOperation: object.globalCompositeOperation, opacity: object.opacity, selectionBackgroundColor: object.selectionBackgroundColor, shadow: object.shadow };
    const groupTransformDone = object.group?._transformDone;
    context.clearRect(0, 0, 3, 3);
    context.save();
    try {
      context.translate(1 - screen.x, 1 - screen.y);
      context.transform(...canvas.viewportTransform);
      object.objectCaching = false;
      object.globalCompositeOperation = "source-over";
      object.selectionBackgroundColor = "";
      object.shadow = null;
      if (object.kloudy?.mask) object.opacity = 1;
      // Render the actual path/image alpha, not its selection box or mask proxy.
      if (object.group) object.group._transformDone = false;
      object.render(context);
      return context.getImageData(1, 1, 1, 1).data[3] > 0;
    } finally {
      Object.assign(object, previous);
      if (object.group) object.group._transformDone = groupTransformDone;
      context.restore();
    }
  }

  global.KfpsFabricAdapter = Object.freeze({
    visiblePixelAt,
    bringObjectToFront,
    cancelObjectTransform,
    major,
    moveObjectTo,
    replaceObjectStack,
    scenePoint,
    sendObjectToBack,
    version,
  });
})(window);
