import math

import numpy as np
from numpy.typing import NDArray

from pymammotion.data.model.location import LocationPoint


class CoordinateConverter:
    """Converts between ENU (East-North-Up) and LLA (Latitude-Longitude-Altitude) coordinate systems.

    Uses WGS84 ellipsoid model for Earth coordinate transformations.
    """

    # WGS84 ellipsoid constants
    WGS84A: float = 6378137.0  # Semi-major axis (equatorial radius) in meters
    FLATTENING: float = 0.0033528106647474805  # WGS84 flattening factor

    def __init__(self, latitude_rad: float, longitude_rad: float, yaw_rad: float = 0.0) -> None:
        """Initialize the coordinate converter.

        Args:
            latitude_rad: Reference latitude in radians
            longitude_rad: Reference longitude in radians
            yaw_rad: Reference yaw angle in radians (default: 0.0)

        """
        # WGS84 ellipsoid parameters
        self.semi_major_axis: float = self.WGS84A
        self.flattening: float = self.FLATTENING
        self.semi_minor_axis: float = (1.0 - self.flattening) * self.WGS84A

        # Eccentricity parameters
        self.first_eccentricity_squared: float = (2.0 - self.flattening) * self.flattening
        self.eccentricity_ratio_squared: float = (1.0 - self.flattening) * (1.0 - self.flattening)
        self.second_eccentricity_squared: float = (self.semi_major_axis**2 - self.semi_minor_axis**2) / (
            self.semi_minor_axis**2
        )

        # Rotation matrix for coordinate transformation
        self.rotation_matrix: NDArray[np.float64] = np.zeros((3, 3), dtype=np.float64)

        # ECEF origin coordinates
        self.x0: float = 0.0
        self.y0: float = 0.0
        self.z0: float = 0.0

        # Yaw angle
        self.yaw: float = yaw_rad

        # Initialize with provided reference point
        self.set_init_lla(latitude_rad, longitude_rad, yaw_rad)

    def set_init_lla(self, latitude_rad: float, longitude_rad: float, yaw_rad: float = 0.0) -> None:
        """Set the initial LLA reference point and yaw angle.

        Args:
            latitude_rad: Reference latitude in radians
            longitude_rad: Reference longitude in radians
            yaw_rad: Reference yaw angle in radians (default: 0.0)

        """
        self.yaw = yaw_rad

        sin_lat = math.sin(latitude_rad)
        cos_lat = math.cos(latitude_rad)
        sin_lon = math.sin(longitude_rad)
        cos_lon = math.cos(longitude_rad)

        # Radius of curvature in the prime vertical
        N = self.semi_major_axis / math.sqrt(1.0 - self.first_eccentricity_squared * (sin_lat**2))

        # Calculate ECEF origin coordinates (altitude = 0)
        horizontal_distance = N * cos_lat
        self.x0 = horizontal_distance * cos_lon
        self.y0 = horizontal_distance * sin_lon
        self.z0 = self.eccentricity_ratio_squared * N * sin_lat

        # Build rotation matrix (ECEF to ENU)
        self.rotation_matrix[0, 0] = -sin_lon
        self.rotation_matrix[0, 1] = cos_lon
        self.rotation_matrix[0, 2] = 0.0

        self.rotation_matrix[1, 0] = -cos_lon * sin_lat
        self.rotation_matrix[1, 1] = -sin_lon * sin_lat
        self.rotation_matrix[1, 2] = cos_lat

        self.rotation_matrix[2, 0] = cos_lon * cos_lat
        self.rotation_matrix[2, 1] = sin_lon * cos_lat
        self.rotation_matrix[2, 2] = sin_lat

    def enu_to_lla(self, east: float, north: float) -> LocationPoint:
        """Convert ENU (East-North-Up) coordinates to LLA (Latitude-Longitude-Altitude).

        Args:
            east: East coordinate in meters
            north: North coordinate in meters

        Returns:
            Point with latitude and longitude in degrees

        """
        # Transform ENU to ECEF (Earth-Centered, Earth-Fixed) coordinates
        # using rotation matrix and origin offset
        ecef_x = self.rotation_matrix[0, 0] * north + self.rotation_matrix[1, 0] * east + self.x0
        ecef_y = self.rotation_matrix[0, 1] * north + self.rotation_matrix[1, 1] * east + self.y0
        ecef_z = self.rotation_matrix[0, 2] * north + self.rotation_matrix[1, 2] * east + self.z0

        # Calculate horizontal distance from Earth's axis
        horizontal_distance = math.hypot(ecef_x, ecef_y)

        # Initial latitude estimate using simplified formula
        initial_latitude = math.atan2(self.semi_major_axis * ecef_z, self.semi_minor_axis * horizontal_distance)

        sin_initial_lat = math.sin(initial_latitude)
        cos_initial_lat = math.cos(initial_latitude)

        # Calculate longitude (straightforward conversion from ECEF)
        longitude_deg = math.degrees(math.atan2(ecef_y, ecef_x))

        # Calculate precise latitude using iterative correction
        # This accounts for Earth's ellipsoidal shape
        latitude_rad = math.atan2(
            ecef_z + self.second_eccentricity_squared * self.semi_minor_axis * (sin_initial_lat**3),
            horizontal_distance - self.first_eccentricity_squared * self.semi_major_axis * (cos_initial_lat**3),
        )
        latitude_deg = math.degrees(latitude_rad)

        return LocationPoint(latitude=latitude_deg, longitude=longitude_deg)

    def lla_to_enu(self, longitude_deg: float, latitude_deg: float) -> list[float]:
        """Convert LLA (Latitude-Longitude-Altitude) to ENU (East-North-Up) coordinates.

        Args:
            longitude_deg: Longitude in degrees
            latitude_deg: Latitude in degrees

        Returns:
            List of [east, north] coordinates in meters

        """
        # Convert to radians
        lat_rad = math.radians(latitude_deg)
        lon_rad = math.radians(longitude_deg)

        sin_lat = math.sin(lat_rad)
        cos_lat = math.cos(lat_rad)
        sin_lon = math.sin(lon_rad)
        cos_lon = math.cos(lon_rad)

        # Calculate radius of curvature
        N = self.semi_major_axis / math.sqrt(1.0 - self.first_eccentricity_squared * (sin_lat**2))

        # Convert to ECEF (altitude = 0)
        horizontal = N * cos_lat
        ecef_x = horizontal * cos_lon
        ecef_y = horizontal * sin_lon
        ecef_z = self.eccentricity_ratio_squared * N * sin_lat

        # Translate to origin
        dx = ecef_x - self.x0
        dy = ecef_y - self.y0
        dz = ecef_z - self.z0

        # Rotate to ENU frame
        east = self.rotation_matrix[0, 0] * dx + self.rotation_matrix[0, 1] * dy + self.rotation_matrix[0, 2] * dz
        north = self.rotation_matrix[1, 0] * dx + self.rotation_matrix[1, 1] * dy + self.rotation_matrix[1, 2] * dz

        # Apply yaw rotation (inverse)
        rotated_east = math.cos(-self.yaw) * east - math.sin(-self.yaw) * north
        rotated_north = math.sin(-self.yaw) * east + math.cos(-self.yaw) * north

        return [round(rotated_east, 3), round(rotated_north, 3)]

    def get_transform_yaw_with_yaw(self, yaw_degrees: float) -> float:
        """Transform a yaw angle from global coordinates to local coordinates.

        This applies the inverse of the reference yaw rotation to convert a global
        heading angle into the local coordinate frame.

        Args:
            yaw_degrees: Input yaw angle in degrees

        Returns:
            Transformed yaw angle in degrees

        """
        # Convert input angle to radians
        yaw_rad = math.radians(yaw_degrees)

        # Apply inverse rotation: -self.yaw
        inverse_yaw = -self.yaw

        # Using angle addition formula: atan2(sin(a+b), cos(a+b))
        # where a = inverse_yaw, b = yaw_rad
        sin_sum = math.sin(inverse_yaw) * math.cos(yaw_rad) + math.cos(inverse_yaw) * math.sin(yaw_rad)
        cos_sum = math.cos(inverse_yaw) * math.cos(yaw_rad) - math.sin(inverse_yaw) * math.sin(yaw_rad)

        # Calculate resulting angle and convert back to degrees
        result_rad = math.atan2(sin_sum, cos_sum)
        result_degrees = math.degrees(result_rad)

        return result_degrees

    def get_angle_yaw(self) -> float:
        """Get the current yaw angle in degrees.

        Returns:
            Yaw angle in degrees

        """
        return math.degrees(self.yaw)

    def get_yaw(self) -> float:
        """Get the current yaw angle in radians.

        Returns:
            Yaw angle in radians

        """
        return self.yaw

    def set_yaw(self, yaw_rad: float) -> None:
        """Set the yaw angle.

        Args:
            yaw_rad: Yaw angle in radians

        """
        self.yaw = yaw_rad

    def set_yaw_degrees(self, yaw_degrees: float) -> None:
        """Set the yaw angle from degrees.

        Args:
            yaw_degrees: Yaw angle in degrees

        """
        self.yaw = math.radians(yaw_degrees)


# Usage example
if __name__ == "__main__":
    # Initialize converter with reference point
    converter = CoordinateConverter(
        latitude_rad=math.radians(40.0), longitude_rad=math.radians(-105.0), yaw_rad=math.radians(45.0)
    )

    # Convert ENU to LLA
    point = converter.enu_to_lla(east=100.0, north=200.0)
    print(f"Latitude: {point.latitude}, Longitude: {point.longitude}")

    # Convert LLA to ENU
    enu = converter.lla_to_enu(longitude_deg=-105.0, latitude_deg=40.0)
    print(f"East: {enu[0]}, North: {enu[1]}")

    # Transform yaw angle
    transformed_yaw = converter.get_transform_yaw_with_yaw(90.0)
    print(f"Transformed yaw: {transformed_yaw}°")
