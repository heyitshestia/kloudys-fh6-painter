package gpu

// evaluateKernelSource contains all OpenCL kernels used by the engine.
//
// evaluate_candidates_v3 (single-pass, analytic):
//   For each candidate (shapeKind, cx, cy, rx, ry, thetaDeg, alpha) it computes the
//   geometrize-style "optimal color" (alpha-weighted mean of the target
//   minus current contribution inside the shape) and the resulting delta
//   error if that shape were drawn over the current canvas.
//
//   Crucially this is done in a SINGLE pass over the bounding box. We
//   accumulate per-channel statistics
//     N    = inside pixel count
//     Σs   = sum of current
//     Σt   = sum of target
//     Σs²  = sum of current squared
//     Σst  = sum of current * target
//   and then derive both the optimal RGB color AND the analytic delta
//   error in O(1) post-loop work via the identity
//
//     Σ ΔErr = α²·[N·c² − 2c·Σs + Σs²] − 2α·[c·Σt − c·Σs − Σst + Σs²]
//
//   which holds for any constant c summed over the ellipse. The alpha
//   channel uses the same identity with c=1 (because out_a blends
//   towards 1 weighted by α, not towards a free color parameter).
//
//   Skipping the second bbox traversal halves the work-item runtime at
//   the cost of ~17 extra register-resident accumulators per work-item.
//
//   Output per candidate: 4 floats { score, R, G, B }. Score is summed
//   over inside pixels (negative = better). Opaque pixels feed the
//   optimal-color statistics; transparent pixels inside the ellipse are
//   counted separately as Nt. Because the FH6 in-game renderer ignores
//   our alpha mask and paints the *full* ellipse, any shape that
//   extends into the transparent region produces a visible halo against
//   whatever body colour the user picked. We therefore HARD REJECT
//   candidates whose overhang exceeds a very small tolerance. The
//   limit is the larger of:
//     - 1 transparent pixel total
//     - ~0.16% of opaque coverage
//   This keeps anti-aliased silhouette edges usable while rejecting
//   the thin out-of-bounds halos that are still visible in FH6.
//
// apply_candidate_v2:
//   Blends a chosen shape into the current canvas. Operates on a tight
//   bounding box and skips transparent pixels.
//
// compute_error_grid:
//   Buckets the per-pixel squared error of (target - current) into a
//   downsampled gridW x gridH buffer. The host side reads it back and
//   uses it to bias random candidate placement towards high-error
//   regions.
const evaluateKernelSource = `
__kernel void evaluate_candidates_v3(
    __global const float4* target,
    __global const float4* current,
    __global const uchar* opaqueMask,
    __global const float* candidates,
    __global float* results,
    const int width,
    const int height
) {
    int gid = get_global_id(0);

    int base = gid * 7;
    int shapeKind = (int)(candidates[base + 0] + 0.5f);
    float cx = candidates[base + 1];
    float cy = candidates[base + 2];
    float rx = fmax(candidates[base + 3], 1.0f);
    float ry = fmax(candidates[base + 4], 1.0f);
    float thetaDeg = candidates[base + 5];
    float ca = clamp(candidates[base + 6], 1e-3f, 1.0f);

    float theta = thetaDeg * 0.01745329251994329577f;
    float cosT = cos(theta);
    float sinT = sin(theta);
    float invRX2 = 1.0f / (rx * rx);
    float invRY2 = 1.0f / (ry * ry);

    float rx2 = rx * rx;
    float ry2 = ry * ry;
    float cos2 = cosT * cosT;
    float sin2 = sinT * sinT;
    float ex = 0.0f;
    float ey = 0.0f;
    if (shapeKind == 1) {
        ex = rx;
        ey = ry;
    } else if (shapeKind == 2) {
        ex = fabs(rx * cosT) + fabs(ry * sinT);
        ey = fabs(rx * sinT) + fabs(ry * cosT);
    } else {
        ex = sqrt(rx2 * cos2 + ry2 * sin2);
        ey = sqrt(rx2 * sin2 + ry2 * cos2);
    }

    int xMin = (int)floor(cx - ex - 1.0f);
    int xMax = (int)ceil(cx + ex + 1.0f);
    int yMin = (int)floor(cy - ey - 1.0f);
    int yMax = (int)ceil(cy + ey + 1.0f);

    xMin = max(0, xMin);
    yMin = max(0, yMin);
    xMax = min(width - 1, xMax);
    yMax = min(height - 1, yMax);

    // Per-channel statistics. 17 floats live in registers across the
    // bbox iteration; modern GPUs have plenty of headroom for this.
    int N = 0;   // opaque pixels inside the ellipse
    int Nt = 0;  // transparent pixels inside the ellipse (penalty bucket)
    float sTR = 0.0f, sTG = 0.0f, sTB = 0.0f, sTA = 0.0f;       // Σ target
    float sCR = 0.0f, sCG = 0.0f, sCB = 0.0f, sCA = 0.0f;       // Σ current
    float sCR2 = 0.0f, sCG2 = 0.0f, sCB2 = 0.0f, sCA2 = 0.0f;   // Σ current²
    float sTCR = 0.0f, sTCG = 0.0f, sTCB = 0.0f, sTCA = 0.0f;   // Σ target·current

    for (int y = yMin; y <= yMax; ++y) {
        int row = y * width;
        float dy = ((float)y + 0.5f) - cy;
        for (int x = xMin; x <= xMax; ++x) {
            float dx = ((float)x + 0.5f) - cx;
            float xr = dx * cosT + dy * sinT;
            float yr = -dx * sinT + dy * cosT;
            int inside = 0;
            if (shapeKind == 1) {
                inside = fabs(dx) <= rx && fabs(dy) <= ry;
            } else if (shapeKind == 2) {
                inside = fabs(xr) <= rx && fabs(yr) <= ry;
            } else if (shapeKind == 8) {
                inside = dx * dx * invRX2 + dy * dy * invRY2 <= 1.0f;
            } else {
                inside = xr * xr * invRX2 + yr * yr * invRY2 <= 1.0f;
            }
            if (!inside) {
                continue;
            }
            int p = row + x;
            if (opaqueMask[p] == 0) {
                Nt++;
                continue;
            }

            float4 t = target[p];
            float4 s = current[p];

            sTR += t.x; sTG += t.y; sTB += t.z; sTA += t.w;
            sCR += s.x; sCG += s.y; sCB += s.z; sCA += s.w;
            sCR2 += s.x * s.x;
            sCG2 += s.y * s.y;
            sCB2 += s.z * s.z;
            sCA2 += s.w * s.w;
            sTCR += t.x * s.x;
            sTCG += t.y * s.y;
            sTCB += t.z * s.z;
            sTCA += t.w * s.w;
            N++;
        }
    }

    // Hard reject:
    //   - shapes covering no opaque pixel at all
    //   - shapes whose transparent overhang exceeds the tighter halo
    //     budget described above
    int maxTransparentPixels = max(1, N / 600);
    if (N == 0 || Nt > maxTransparentPixels) {
        results[gid * 4 + 0] = 3.402823466e+38f;
        results[gid * 4 + 1] = 0.0f;
        results[gid * 4 + 2] = 0.0f;
        results[gid * 4 + 3] = 0.0f;
        return;
    }

    float Nf = (float)N;
    float invN = 1.0f / Nf;
    float invA = 1.0f - ca;

    // Optimal RGB color: c = (mean(t) − mean(s)·(1−α)) / α  (clamped).
    // The clamped color is what will actually be rendered, so we plug
    // that same value into the analytic ΔErr formula below — the
    // identity holds for any constant c, not just the unclamped optimum.
    float oR = clamp((sTR * invN - (sCR * invN) * invA) / ca, 0.0f, 1.0f);
    float oG = clamp((sTG * invN - (sCG * invN) * invA) / ca, 0.0f, 1.0f);
    float oB = clamp((sTB * invN - (sCB * invN) * invA) / ca, 0.0f, 1.0f);

    // Σ ΔErr = α²·[N·c² − 2c·Σs + Σs²] − 2α·[c·Σt − c·Σs − Σst + Σs²]
    //
    // RGB channels use the optimised c above. The alpha channel blends
    // toward 1 (out_a = s_a·(1−α) + α), so we substitute c = 1 below.
    float a2 = ca * ca;
    float two_a = 2.0f * ca;

    float dR = a2 * (Nf*oR*oR - 2.0f*oR*sCR + sCR2)
             - two_a * (oR*sTR - oR*sCR - sTCR + sCR2);
    float dG = a2 * (Nf*oG*oG - 2.0f*oG*sCG + sCG2)
             - two_a * (oG*sTG - oG*sCG - sTCG + sCG2);
    float dB = a2 * (Nf*oB*oB - 2.0f*oB*sCB + sCB2)
             - two_a * (oB*sTB - oB*sCB - sTCB + sCB2);
    float dA = a2 * (Nf - 2.0f*sCA + sCA2)
             - two_a * (sTA - sCA - sTCA + sCA2);

    float totalDelta = dR + dG + dB + dA;

    // Soft penalty within the tolerance budget: each remaining
    // transparent pixel still adds a stronger α²-weighted cost so that
    // the optimiser aggressively prefers zero overhang even when the
    // opaque-side error is otherwise tied.
    if (Nt > 0) {
        float penalty = 6.0f * a2 * ((float)Nt) * (oR*oR + oG*oG + oB*oB + 1.0f);
        totalDelta += penalty;
    }

    results[gid * 4 + 0] = totalDelta;
    results[gid * 4 + 1] = oR;
    results[gid * 4 + 2] = oG;
    results[gid * 4 + 3] = oB;
}

#define WG_SIZE 256

__kernel void evaluate_candidates_v4(
    __global const float4* target,
    __global const float4* current,
    __global const uchar* opaqueMask,
    __global const float* candidates,
    __global float* results,
    const int width,
    const int height
) {
    int gid = get_group_id(0);
    int lid = get_local_id(1) * get_local_size(0) + get_local_id(0);

    int base = gid * 7;
    int shapeKind = (int)(candidates[base + 0] + 0.5f);
    float cx = candidates[base + 1];
    float cy = candidates[base + 2];
    float rx = fmax(candidates[base + 3], 1.0f);
    float ry = fmax(candidates[base + 4], 1.0f);
    float thetaDeg = candidates[base + 5];
    float ca = clamp(candidates[base + 6], 1e-3f, 1.0f);

    float theta = thetaDeg * 0.01745329251994329577f;
    float cosT = cos(theta);
    float sinT = sin(theta);
    float invRX2 = 1.0f / (rx * rx);
    float invRY2 = 1.0f / (ry * ry);

    float rx2 = rx * rx;
    float ry2 = ry * ry;
    float cos2 = cosT * cosT;
    float sin2 = sinT * sinT;
    float ex = 0.0f;
    float ey = 0.0f;
    if (shapeKind == 1) {
        ex = rx;
        ey = ry;
    } else if (shapeKind == 2) {
        ex = fabs(rx * cosT) + fabs(ry * sinT);
        ey = fabs(rx * sinT) + fabs(ry * cosT);
    } else {
        ex = sqrt(rx2 * cos2 + ry2 * sin2);
        ey = sqrt(rx2 * sin2 + ry2 * cos2);
    }

    int xMin = (int)floor(cx - ex - 1.0f);
    int xMax = (int)ceil(cx + ex + 1.0f);
    int yMin = (int)floor(cy - ey - 1.0f);
    int yMax = (int)ceil(cy + ey + 1.0f);

    xMin = max(0, xMin);
    yMin = max(0, yMin);
    xMax = min(width - 1, xMax);
    yMax = min(height - 1, yMax);

    int bw = max(xMax - xMin + 1, 1);
    int totalCells = bw * max(yMax - yMin + 1, 1);

    int N = 0, Nt = 0;
    float sTR = 0.0f, sTG = 0.0f, sTB = 0.0f, sTA = 0.0f;
    float sCR = 0.0f, sCG = 0.0f, sCB = 0.0f, sCA = 0.0f;
    float sCR2 = 0.0f, sCG2 = 0.0f, sCB2 = 0.0f, sCA2 = 0.0f;
    float sTCR = 0.0f, sTCG = 0.0f, sTCB = 0.0f, sTCA = 0.0f;

    for (int ci = lid; ci < totalCells; ci += WG_SIZE) {
        int ly = ci / bw;
        int lx = ci % bw;
        int x = xMin + lx;
        int y = yMin + ly;

        float dx = ((float)x + 0.5f) - cx;
        float dy = ((float)y + 0.5f) - cy;
        float xr = dx * cosT + dy * sinT;
        float yr = -dx * sinT + dy * cosT;
        int inside = 0;
        if (shapeKind == 1) {
            inside = fabs(dx) <= rx && fabs(dy) <= ry;
        } else if (shapeKind == 2) {
            inside = fabs(xr) <= rx && fabs(yr) <= ry;
        } else if (shapeKind == 8) {
            inside = dx * dx * invRX2 + dy * dy * invRY2 <= 1.0f;
        } else {
            inside = xr * xr * invRX2 + yr * yr * invRY2 <= 1.0f;
        }
        if (!inside) {
            continue;
        }
        int p = y * width + x;
        if (opaqueMask[p] == 0) {
            Nt++;
            continue;
        }

        float4 t = target[p];
        float4 s = current[p];

        sTR += t.x; sTG += t.y; sTB += t.z; sTA += t.w;
        sCR += s.x; sCG += s.y; sCB += s.z; sCA += s.w;
        sCR2 += s.x * s.x; sCG2 += s.y * s.y;
        sCB2 += s.z * s.z; sCA2 += s.w * s.w;
        sTCR += t.x * s.x; sTCG += t.y * s.y;
        sTCB += t.z * s.z; sTCA += t.w * s.w;
        N++;
    }

    __local float l_data[WG_SIZE * 18];
    int off = lid * 18;
    l_data[off +  0] = (float)N;  l_data[off +  1] = (float)Nt;
    l_data[off +  2] = sTR;       l_data[off +  3] = sTG;
    l_data[off +  4] = sTB;       l_data[off +  5] = sTA;
    l_data[off +  6] = sCR;       l_data[off +  7] = sCG;
    l_data[off +  8] = sCB;       l_data[off +  9] = sCA;
    l_data[off + 10] = sCR2;      l_data[off + 11] = sCG2;
    l_data[off + 12] = sCB2;      l_data[off + 13] = sCA2;
    l_data[off + 14] = sTCR;      l_data[off + 15] = sTCG;
    l_data[off + 16] = sTCB;      l_data[off + 17] = sTCA;

    barrier(CLK_LOCAL_MEM_FENCE);

    for (int stride = WG_SIZE / 2; stride > 0; stride >>= 1) {
        if (lid < stride) {
            int a = lid * 18;
            int b = (lid + stride) * 18;
            for (int k = 0; k < 18; k++) {
                l_data[a + k] += l_data[b + k];
            }
        }
        barrier(CLK_LOCAL_MEM_FENCE);
    }

    if (lid != 0) {
        return;
    }

    N  = (int)l_data[0];   Nt = (int)l_data[1];
    sTR = l_data[2];  sTG = l_data[3];  sTB = l_data[4];  sTA = l_data[5];
    sCR = l_data[6];  sCG = l_data[7];  sCB = l_data[8];  sCA = l_data[9];
    sCR2= l_data[10]; sCG2= l_data[11]; sCB2= l_data[12]; sCA2= l_data[13];
    sTCR= l_data[14]; sTCG= l_data[15]; sTCB= l_data[16]; sTCA= l_data[17];

    int maxTransparentPixels = max(1, N / 600);
    if (N == 0 || Nt > maxTransparentPixels) {
        results[gid * 4 + 0] = 3.402823466e+38f;
        results[gid * 4 + 1] = 0.0f;
        results[gid * 4 + 2] = 0.0f;
        results[gid * 4 + 3] = 0.0f;
        return;
    }

    float Nf = (float)N;
    float invN = 1.0f / Nf;
    float invA = 1.0f - ca;

    float oR = clamp((sTR * invN - (sCR * invN) * invA) / ca, 0.0f, 1.0f);
    float oG = clamp((sTG * invN - (sCG * invN) * invA) / ca, 0.0f, 1.0f);
    float oB = clamp((sTB * invN - (sCB * invN) * invA) / ca, 0.0f, 1.0f);

    float a2 = ca * ca;
    float two_a = 2.0f * ca;

    float dR = a2 * (Nf*oR*oR - 2.0f*oR*sCR + sCR2)
             - two_a * (oR*sTR - oR*sCR - sTCR + sCR2);
    float dG = a2 * (Nf*oG*oG - 2.0f*oG*sCG + sCG2)
             - two_a * (oG*sTG - oG*sCG - sTCG + sCG2);
    float dB = a2 * (Nf*oB*oB - 2.0f*oB*sCB + sCB2)
             - two_a * (oB*sTB - oB*sCB - sTCB + sCB2);
    float dA = a2 * (Nf - 2.0f*sCA + sCA2)
             - two_a * (sTA - sCA - sTCA + sCA2);

    float totalDelta = dR + dG + dB + dA;
    if (Nt > 0) {
        totalDelta += 6.0f * a2 * ((float)Nt) * (oR*oR + oG*oG + oB*oB + 1.0f);
    }

    results[gid * 4 + 0] = totalDelta;
    results[gid * 4 + 1] = oR;
    results[gid * 4 + 2] = oG;
    results[gid * 4 + 3] = oB;
}

__kernel void apply_candidate_v2(
    __global float4* current,
    __global const uchar* opaqueMask,
    const int width,
    const int height,
    const int shapeKind,
    const int xMin,
    const int yMin,
    const int xMax,
    const int yMax,
    const float cx,
    const float cy,
    const float rxRaw,
    const float ryRaw,
    const float thetaDeg,
    const float cr,
    const float cg,
    const float cb,
    const float ca
) {
    int lx = get_global_id(0);
    int ly = get_global_id(1);
    int bw = xMax - xMin + 1;
    int bh = yMax - yMin + 1;
    if (lx >= bw || ly >= bh) {
        return;
    }
    int x = xMin + lx;
    int y = yMin + ly;
    int p = y * width + x;
    if (opaqueMask[p] == 0) {
        return;
    }

    float rx = fmax(rxRaw, 1.0f);
    float ry = fmax(ryRaw, 1.0f);
    float theta = thetaDeg * 0.01745329251994329577f;
    float cosT = cos(theta);
    float sinT = sin(theta);
    float invRX2 = 1.0f / (rx * rx);
    float invRY2 = 1.0f / (ry * ry);

    float dx = ((float)x + 0.5f) - cx;
    float dy = ((float)y + 0.5f) - cy;
    float xr = dx * cosT + dy * sinT;
    float yr = -dx * sinT + dy * cosT;
    int inside = 0;
    if (shapeKind == 1) {
        inside = fabs(dx) <= rx && fabs(dy) <= ry;
    } else if (shapeKind == 2) {
        inside = fabs(xr) <= rx && fabs(yr) <= ry;
    } else if (shapeKind == 8) {
        inside = dx * dx * invRX2 + dy * dy * invRY2 <= 1.0f;
    } else {
        inside = xr * xr * invRX2 + yr * yr * invRY2 <= 1.0f;
    }
    if (!inside) {
        return;
    }

    float4 src = current[p];
    float alpha = clamp(ca, 0.0f, 1.0f);
    float invA = 1.0f - alpha;
    src.x = src.x * invA + clamp(cr, 0.0f, 1.0f) * alpha;
    src.y = src.y * invA + clamp(cg, 0.0f, 1.0f) * alpha;
    src.z = src.z * invA + clamp(cb, 0.0f, 1.0f) * alpha;
    src.w = src.w * invA + alpha;
    current[p] = src;
}

__kernel void compute_error_grid(
    __global const float4* target,
    __global const float4* current,
    __global const uchar* opaqueMask,
    __global float* gridOut,
    const int width,
    const int height,
    const int gridW,
    const int gridH
) {
    int gx = get_global_id(0);
    int gy = get_global_id(1);
    if (gx >= gridW || gy >= gridH) {
        return;
    }

    int x0 = (int)(((long)gx * (long)width) / (long)gridW);
    int x1 = (int)(((long)(gx + 1) * (long)width) / (long)gridW);
    int y0 = (int)(((long)gy * (long)height) / (long)gridH);
    int y1 = (int)(((long)(gy + 1) * (long)height) / (long)gridH);

    float sum = 0.0f;
    for (int y = y0; y < y1; ++y) {
        int row = y * width;
        for (int x = x0; x < x1; ++x) {
            int p = row + x;
            if (opaqueMask[p] == 0) {
                continue;
            }
            float4 t = target[p];
            float4 s = current[p];
            float dr = t.x - s.x;
            float dg = t.y - s.y;
            float db = t.z - s.z;
            float da = t.w - s.w;
            sum += dr * dr + dg * dg + db * db + da * da;
        }
    }
    gridOut[gy * gridW + gx] = sum;
}
`
