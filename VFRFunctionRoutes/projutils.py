from typing import NamedTuple
import numpy as np
import math



class PointLonLat(NamedTuple):
    lon: float
    lat: float


class PointXY(NamedTuple):
    x: float
    y: float

class ExtentLonLat(NamedTuple):
    minlon: float
    minlat: float
    maxlon: float
    maxlat: float


class ExtentXY(NamedTuple):
    minx: float
    miny: float
    maxx: float
    maxy: float

def _rotate_point(point, center, angle_degrees):
    """
    Rotate a point around another point in a 2D coordinate system.

    Parameters:
    - point: Tuple (x, y) representing the point to be rotated.
    - center: Tuple (cx, cy) representing the center of rotation.
    - angle_degrees: The angle in degrees by which to rotate the point.

    Returns:
    - rotated_point: Tuple (x', y') representing the rotated point.
    """
    x, y = point
    cx, cy = center

    # Convert angle from degrees to radians
    angle_radians = math.radians(angle_degrees)

    # Perform the rotation using the rotation matrix
    rotated_x = (x - cx) * math.cos(angle_radians) - \
        (y - cy) * math.sin(angle_radians) + cx
    rotated_y = (x - cx) * math.sin(angle_radians) + \
        (y - cy) * math.cos(angle_radians) + cy

    rotated_point = (rotated_x, rotated_y)

    return rotated_point


def _calculate_2d_transformation_matrix(source_points: list[tuple[float, float]], destination_points: list[tuple[float, float]]):
    """
    Calculate a 2D transformation matrix given two sets of corresponding points in source and destination coordinate systems.

    Parameters:
    - source_points: List of tuples (x, y) representing points in the source coordinate system.
    - destination_points: List of tuples (x, y) representing corresponding points in the destination coordinate system.

    Returns:
    - transformation_matrix: 3x3 numpy array representing the 2D transformation matrix.
    """
    if len(source_points) != len(destination_points) or len(source_points) < 2:
        raise ValueError(
            "Invalid input. Must have at least 2 corresponding points.")

    A = np.zeros((len(source_points), 3))
    B = np.zeros((len(source_points), 3))

    for i in range(len(source_points)):
        x_s, y_s = source_points[i]
        x_d, y_d = destination_points[i]

        A[i] = [x_s, y_s, 1]
        B[i] = [x_d, y_d, 1]

    transformation_matrix, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
    transformation_matrix = np.transpose(transformation_matrix)

    return transformation_matrix


def _apply_transformation_matrix(point, transformation_matrix):
    """
    Apply a 2D transformation matrix to a point.

    Parameters:
    - point: Tuple (x, y) representing the original point.
    - transformation_matrix: 3x3 numpy array representing the 2D transformation matrix.

    Returns:
    - transformed_point: Tuple (x', y') representing the transformed point.
    """
    point_vector = np.array([point[0], point[1], 1])
    transformed_point_vector = np.dot(transformation_matrix, point_vector)

    # Extract x' and y' from the transformed point vector
    transformed_point = (
        transformed_point_vector[0], transformed_point_vector[1])

    return transformed_point


def _get_extent_from_points(points: list[PointLonLat]) -> ExtentLonLat:
    min_lat, max_lat, min_lon, max_lon = None, None, None, None
    for p in points:
        min_lat = min(min_lat, p.lat) if min_lat else p.lat
        max_lat = max(max_lat, p.lat) if max_lat else p.lat
        min_lon = min(min_lon, p.lon) if min_lon else p.lon
        max_lon = max(max_lon, p.lon) if max_lon else p.lon
    return ExtentLonLat(min_lon, min_lat, max_lon, max_lat)


def _get_extent_from_extents(extents: list[ExtentLonLat]) -> ExtentLonLat:
    if len(extents) == 0:
        return ExtentLonLat(None, None, None, None)
    min_lat, max_lat, min_lon, max_lon = None, None, None, None
    for ex in extents:
        min_lat = min(n for n in [min_lat, ex.minlat, ex.maxlat] if n is not None)
        max_lat = max(n for n in [max_lat, ex.minlat, ex.maxlat] if n is not None)
        min_lon = min(n for n in [min_lon, ex.minlon, ex.maxlon] if n is not None)
        max_lon = max(n for n in [max_lon, ex.minlon, ex.maxlon] if n is not None)
    return ExtentLonLat(min_lon, min_lat, max_lon, max_lat)
