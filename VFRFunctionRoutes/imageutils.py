import os
import numpy as np

USE_NUMBA = os.getenv('USE_NUMBA', 'True').lower() in ['true', 'yes', '1', 'on']

if USE_NUMBA:
    from numba import njit
    dojit = njit
else:
    def dojit(func):
        """no-op decorator"""
        return func
    

@dojit
def alpha_composite_np_loops(dest, src, x=0, y=0):
    """
    In-place alpha composite `src` over `dst` using nested loops.
    Works entirely in-place, no full-size buffers allocated.
    Both arrays must be RGBA uint8.
    """
    H, W, _ = dest.shape
    h, w, _ = src.shape

    for j in range(h):
        y_dst = y + j
        if y_dst < 0 or y_dst >= H:
            continue
        for i in range(w):
            x_dst = x + i
            if x_dst < 0 or x_dst >= W:
                continue

            sr, sg, sb, sa = src[j, i, 0], src[j,
                                               i, 1], src[j, i, 2], src[j, i, 3]
            dr, dg, db, da = dest[y_dst, x_dst, 0], dest[y_dst,
                                                         x_dst, 1], dest[y_dst, x_dst, 2], dest[y_dst, x_dst, 3]

            inv_sa = 255 - sa
            out_a = sa + da * inv_sa // 255

            if out_a == 0:
                dest[y_dst, x_dst, 0] = 0
                dest[y_dst, x_dst, 1] = 0
                dest[y_dst, x_dst, 2] = 0
                dest[y_dst, x_dst, 3] = 0
            else:
                out_r = (sr*sa + dr*da*inv_sa // 255)//out_a
                out_g = (sg*sa + dg*da*inv_sa // 255)//out_a
                out_b = (sb*sa + db*da*inv_sa // 255)//out_a
                dest[y_dst, x_dst, 0] = out_r
                dest[y_dst, x_dst, 1] = out_g
                dest[y_dst, x_dst, 2] = out_b
                dest[y_dst, x_dst, 3] = out_a


@dojit
def paste_img(dest: np.ndarray, src: np.ndarray, x: int, y: int):
    H, W, _ = dest.shape
    h, w, _ = src.shape

    x0 = max(x, 0)
    y0 = max(y, 0)
    x1 = min(x + w, W)
    y1 = min(y + h, H)

    sx0 = x0 - x
    sy0 = y0 - y

    for j in range(y0, y1):
        for i in range(x0, x1):
            dest[j, i, 0] = src[sy0 + (j - y0), sx0 + (i - x0), 0]
            dest[j, i, 1] = src[sy0 + (j - y0), sx0 + (i - x0), 1]
            dest[j, i, 2] = src[sy0 + (j - y0), sx0 + (i - x0), 2]
            dest[j, i, 3] = src[sy0 + (j - y0), sx0 + (i - x0), 3]


# precompile both to avoid later memory spikes
dummy_dst = np.zeros((1, 1, 4), dtype=np.uint8)
dummy_src = np.zeros((1, 1, 4), dtype=np.uint8)
paste_img(dummy_dst, dummy_src, 0, 0)
alpha_composite_np_loops(dummy_dst, dummy_src, 0, 0)
del dummy_src, dummy_dst
