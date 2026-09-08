"""Image-only operations; no Qt, downloads or process access."""
from __future__ import annotations

import numpy as np
from PIL import Image


def model_input(image):
    # Published ISNet/rembg normalization; keep it identical for model compatibility.
    if image.mode == "RGBA" and image.getchannel("A").getextrema()[0] < 255:
        background = Image.new("RGBA", image.size, "white")
        background.alpha_composite(image)
        image = background
    rgb = np.asarray(image.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS), dtype=np.float32)
    rgb /= max(float(rgb.max()), 1e-6)
    rgb -= np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
    return np.ascontiguousarray(rgb.transpose(2, 0, 1)[None])


def alpha_from_prediction(prediction, size):
    mask = np.asarray(prediction, dtype=np.float32).squeeze()
    if mask.shape != (1024, 1024) or not np.isfinite(mask).all():
        raise ValueError("The model returned an invalid foreground mask.")
    low, high = float(mask.min()), float(mask.max())
    if high - low < 1e-12:
        raise ValueError("The model could not distinguish a foreground subject in this image.")
    pixels = ((mask - low) * (255 / (high - low))).clip(0, 255).astype(np.uint8)
    return Image.fromarray(pixels).resize(size, Image.Resampling.LANCZOS)


def compose_result(image, alpha, cleanup=False):
    original = np.asarray(image)
    # Refinement is subtractive: it must never resurrect already transparent pixels.
    values = np.minimum(np.asarray(alpha), original[:, :, 3]).copy()
    if cleanup:
        import cv2
        core = (values >= 128).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(core, connectivity=8)
        if count > 1:
            cutoff = max(2, int(stats[1:, cv2.CC_STAT_AREA].max() * 0.001))
            remove = stats[:, cv2.CC_STAT_AREA] < cutoff
            remove[0] = False
            # Attach soft edge pixels to their nearest confident component. Tiny
            # alpha bridges must not merge otherwise disconnected fragments.
            if np.any(remove):
                _, nearest = cv2.distanceTransformWithLabels(1-core, cv2.DIST_L2, 5,
                                                             labelType=cv2.DIST_LABEL_CCOMP)
                lookup = np.zeros(int(nearest.max())+1, dtype=bool)
                lookup[nearest[core > 0]] = remove[labels[core > 0]]
                values[lookup[nearest]] = 0
    result = image.copy()
    result.putalpha(Image.fromarray(values))
    validate_result(image, result)
    return result


def validate_result(original, result, color_edges=False):
    before, after = np.asarray(original), np.asarray(result)
    if result.mode != "RGBA" or result.size != original.size:
        raise ValueError("The output dimensions or transparency are invalid.")
    changed = np.any(before[:, :, :3] != after[:, :, :3], axis=2)
    if np.any(changed & (~(after[:, :, 3] < before[:, :, 3]) if color_edges else True)):
        raise ValueError("Background removal unexpectedly changed image colors.")
    if np.any(after[:, :, 3] > before[:, :, 3]):
        raise ValueError("Background removal unexpectedly revealed transparent pixels.")
    if not after[:, :, 3].any():
        raise ValueError("No foreground was detected. The original image is unchanged.")


def refine_illustration(image, alpha):
    """Subtractive colour-boundary refinement, with confident model pixels fixed."""
    import cv2
    small = image.convert("RGB")
    small.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
    values = np.asarray(alpha.resize(small.size, Image.Resampling.LANCZOS))
    if np.count_nonzero(values >= 240) < 32 or np.count_nonzero(values < 8) < 32:
        return alpha
    labels = np.where(values >= 128, cv2.GC_PR_FGD, cv2.GC_PR_BGD).astype(np.uint8)
    labels[values >= 240] = cv2.GC_FGD
    labels[values < 8] = cv2.GC_BGD
    cv2.setRNGSeed(0)
    cv2.grabCut(np.asarray(small), labels, None, np.zeros((1,65)), np.zeros((1,65)), 3, cv2.GC_INIT_WITH_MASK)
    keep = ((labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD)).astype(np.uint8)*255
    refined = Image.fromarray(keep).resize(image.size, Image.Resampling.LANCZOS)
    return Image.fromarray(np.minimum(np.asarray(alpha), np.asarray(refined)))


def background_color(image):
    """Dominant border colour, not the average of foreground and background."""
    sample = image.copy()
    sample.thumbnail((512, 512))
    rgba = np.asarray(sample.convert("RGBA"))
    border = np.concatenate((rgba[0], rgba[-1], rgba[:,0], rgba[:,-1]))
    pixels = border[border[:,3] >= 128, :3]
    if len(pixels) == 0:
        return "#ffffff"
    bins = pixels.astype(np.int32)//8
    codes = bins[:,0]*1024 + bins[:,1]*32 + bins[:,2]
    winner = np.bincount(codes).argmax()
    rgb = np.median(pixels[codes == winner], axis=0).astype(int)
    return "#" + "".join(f"{v:02x}" for v in rgb)


def color_result(image, color, tolerance=12, enclosed=True, decontaminate=True):
    """Remove a flat key colour, including optional enclosed regions and edge spill."""
    import cv2
    from PIL import ImageColor
    rgb = np.asarray(image.convert("RGB"))
    key = np.asarray(ImageColor.getrgb(color), dtype=np.float32)
    original_alpha = np.asarray(image.getchannel("A"))
    distance = np.max(np.abs(rgb.astype(np.int16)-key.astype(np.int16)), axis=2)
    background = (distance <= tolerance) | (original_alpha == 0)
    if not enclosed:
        _, labels = cv2.connectedComponents(background.astype(np.uint8), connectivity=4)
        edge_labels = np.unique(np.concatenate((labels[0], labels[-1], labels[:,0], labels[:,-1])))
        edge_labels = edge_labels[edge_labels != 0]
        background = np.isin(labels, edge_labels)
    foreground = (~background).astype(np.uint8)
    if not foreground.any():
        raise ValueError("No foreground remains at this tolerance. Lower it or choose a different background colour.")
    alpha = foreground * 255
    output_rgb = rgb.copy()
    if decontaminate:
        # Interior colours are untouched. Only a narrow edge band is unmatted
        # against the selected background, using the nearest interior as a guide.
        core = cv2.erode(foreground, np.ones((3,3), np.uint8), iterations=2)
        count, components = cv2.connectedComponents(foreground, connectivity=8)
        has_core = np.zeros(count, dtype=bool)
        has_core[components[core > 0]] = True
        has_core[0] = True
        if np.any(~has_core):
            # Thin lettering may have no eroded interior. Its most contrasting
            # pixels provide a local colour reference without borrowing another letter.
            contrast = np.zeros(count, dtype=distance.dtype)
            np.maximum.at(contrast, components.ravel(), distance.ravel())
            core[(~has_core[components]) & (distance >= contrast[components])] = 1
        if core.any():
            dist, nearest = cv2.distanceTransformWithLabels(1-core, cv2.DIST_L2, 5,
                                                           labelType=cv2.DIST_LABEL_PIXEL)
            edge = (dist <= 4) & (core == 0)
            if not enclosed:
                edge &= cv2.dilate(background.astype(np.uint8), np.ones((9,9), np.uint8)).astype(bool)
            colors = np.zeros((int(nearest.max())+1, 3), dtype=np.float32)
            colors[nearest[core > 0]] = rgb[core > 0]
            fg = colors[nearest[edge]]
            pixels = rgb[edge].astype(np.float32)
            vector = fg - key
            fraction = np.sum((pixels-key)*vector, axis=1)/np.maximum(np.sum(vector*vector, axis=1), 1)
            fraction = fraction.clip(0,1)
            recovered = (pixels - (1-fraction[:,None])*key)/np.maximum(fraction[:,None], 1/255)
            edge_alpha = np.rint(fraction*255).astype(np.uint8)
            alpha[edge] = edge_alpha
            changed = edge_alpha < 255
            edge_colors = rgb[edge].copy()
            edge_colors[changed] = np.rint(recovered[changed]).clip(0,255).astype(np.uint8)
            output_rgb[edge] = edge_colors
    alpha = np.minimum(alpha, original_alpha)
    # Colour changes are only allowed where this operation actually removed alpha.
    output_rgb[alpha >= original_alpha] = rgb[alpha >= original_alpha]
    result = Image.fromarray(np.dstack((output_rgb, alpha)))
    validate_result(image, result, color_edges=True)
    return result


def quality_warning(result):
    values = np.asarray(result.getchannel("A"))
    visible = int(np.count_nonzero(values >= 128))
    mass = float(values.sum(dtype=np.float64)/255)
    if visible < max(8, values.size*0.0001) or mass < max(8, values.size*0.0001):
        return "Almost no visible foreground remains. Review the result, choose Logo / flat colour for lettering, or restore missing areas."
    return ""
