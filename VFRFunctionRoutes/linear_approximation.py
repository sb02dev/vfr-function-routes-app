import numpy as np
import matplotlib.pyplot as plt


##########################
### RDP Implementation ###
##########################
def perpendicular_distance(point, start, end):
    """Compute perpendicular distance of a point to a line segment (start–end)."""
    if np.all(start == end):
        return np.linalg.norm(point - start)
    return np.abs(np.cross(end - start, start - point)) / np.linalg.norm(end - start)

def rdp(points, epsilon):
    """Ramer–Douglas–Peucker algorithm.
    points: Nx2 numpy array of [x, y] points
    epsilon: max allowed error (tolerance)
    """
    start, end = points[0], points[-1]
    dmax, index = 0, 0
    for i in range(1, len(points) - 1):
        d = perpendicular_distance(points[i], start, end)
        if d > dmax:
            index, dmax = i, d

    if dmax > epsilon:
        left = rdp(points[:index+1], epsilon)
        right = rdp(points[index:], epsilon)
        return np.vstack((left[:-1], right))
    else:
        return np.array([start, end])

def fit_segments(points, breakpoints):
    """Fit least-squares line segments between breakpoints.
    Returns new set of points approximating the function."""
    approx_x = []
    approx_y = []
    for i in range(len(breakpoints)-1):
        # segment indices
        mask = (points[:,0] >= breakpoints[i,0]) & (points[:,0] <= breakpoints[i+1,0])
        seg = points[mask]

        # least-squares line fit: y = m*x + b
        A = np.vstack([seg[:,0], np.ones_like(seg[:,0])]).T
        m, b = np.linalg.lstsq(A, seg[:,1], rcond=None)[0]

        # build fitted line
        xs = seg[:,0]
        ys = m*xs + b

        approx_x.extend(xs)
        approx_y.extend(ys)

    return np.array(approx_x), np.array(approx_y)


#########################
### DP Implementation ###
#########################
def segment_fit_error(x, y):
    """Return slope, intercept, and squared error of best-fit line for (x,y)."""
    A = np.vstack([x, np.ones_like(x)]).T
    m, b = np.linalg.lstsq(A, y, rcond=None)[0]
    y_fit = m*x + b
    error = np.sum((y - y_fit)**2)
    return m, b, error


def precompute_costs(x, y):
    """Precompute least-squares error for every interval [i,j]."""
    n = len(x)
    costs = np.zeros((n, n))
    params = {}
    for i in range(n):
        for j in range(i+1, n):
            m, b, err = segment_fit_error(x[i:j+1], y[i:j+1])
            costs[i, j] = err
            params[(i, j)] = (m, b)
    return costs, params


def piecewise_linear_fit(x, y, K):
    """Optimal piecewise linear fit with K segments (DP)."""
    n = len(x)
    costs, params = precompute_costs(x, y)

    # DP table
    dp = np.full((K+1, n), np.inf)
    prev = np.full((K+1, n), -1, dtype=int)
    dp[0, 0] = 0

    for k in range(1, K+1):
        for j in range(1, n):
            for i in range(j):
                cost = dp[k-1, i] + costs[i, j]
                if cost < dp[k, j]:
                    dp[k, j] = cost
                    prev[k, j] = i

    # Backtrack
    segments = []
    k, j = K, n-1
    while k > 0:
        i = prev[k, j]
        m, b = params[(i, j)]
        segments.append((x[i], x[j], m, b))
        j = i
        k -= 1
    segments.reverse()
    return segments



#####################
### Example usage ###
#####################
def example_rdp():
    # ---- Example usage ----
    f = np.sin
    x = np.linspace(0, 2*np.pi, 500)
    y = f(x)
    points = np.column_stack((x, y))

    epsilon = 0.025
    breakpoints = rdp(points, epsilon)  # detect breakpoints
    #approx_x, approx_y = fit_segments(points, breakpoints)
    approx_x, approx_y = breakpoints[:,0], breakpoints[:,1]

    # Plot
    plt.figure(figsize=(10,5))
    plt.plot(x, y, label="Original function", alpha=0.7)
    plt.plot(approx_x, approx_y, 'r-', label="RDP + least-squares fit")
    plt.scatter(breakpoints[:,0], breakpoints[:,1], color="red", s=40, label="Breakpoints")
    plt.legend()
    plt.show()


def example_dp():
    # ---- Example usage ----
    f = np.sin
    x = np.linspace(0, 2*np.pi, 200)
    y = f(x)

    K = 10   # number of segments
    segments = piecewise_linear_fit(x, y, K)

    # Build approximation
    approx_x, approx_y = [], []
    for (x0, x1, m, b) in segments:
        xs = x[(x >= x0) & (x <= x1)]
        ys = m*xs + b
        approx_x.extend(xs)
        approx_y.extend(ys)

    plt.figure(figsize=(10, 5))
    plt.plot(x, y, label="Original function", alpha=0.7)
    plt.plot(approx_x, approx_y, 'r-', label=f"{K}-segment optimal fit")
    for (x0, x1, m, b) in segments:
        plt.axvline(x0, color='gray', linestyle='--', alpha=0.4)
    plt.legend()
    plt.show()

    print("Segments (x_start, x_end, slope, intercept):")
    for seg in segments:
        print(seg)

if __name__=="__main__":
    example_rdp()
    example_dp()