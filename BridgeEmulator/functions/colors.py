from typing import List

def rgbBrightness(rgb: List[int], brightness: float) -> List[int]:
    """
    Adjust the brightness of an RGB color.

    Args:
        rgb: List of RGB values [R, G, B].
        brightness: Brightness factor.

    Returns:
        List of adjusted RGB values.
    """
    return [min(max((int(color * brightness)) >> 8, 0), 255) for color in rgb]

def clampRGB(rgb: List[float]) -> List[int]:
    """
    Clamp RGB values to the range [0, 255].

    Args:
        rgb: List of RGB values [R, G, B].

    Returns:
        List of clamped RGB values.
    """
    return [min(max(int(color), 0), 255) for color in rgb]

def convert_rgb_xy(red: float, green: float, blue: float) -> List[float]:
    """
    Convert RGB values to XY color space.

    Args:
        red: Red value.
        green: Green value.
        blue: Blue value.

    Returns:
        List of XY values [x, y].
    """
    def correct_gamma(value: float) -> float:
        return pow((value + 0.055) / (1.0 + 0.055), 2.4) if value > 0.04045 else value / 12.92

    red, green, blue = map(correct_gamma, [red, green, blue])

    X = red * 0.664511 + green * 0.154324 + blue * 0.162028
    Y = red * 0.283881 + green * 0.668433 + blue * 0.047685
    Z = red * 0.000088 + green * 0.072310 + blue * 0.986039

    div = X + Y + Z
    if div < 0.000001:
        return [0, 0]
    return [X / div, Y / div]

def convert_xy(x: float, y: float, bri: float) -> List[int]:
    """
    Convert XY values to RGB color space.

    Args:
        x: X value.
        y: Y value.
        bri: Brightness factor.

    Returns:
        List of RGB values [R, G, B].
    """
    X, Y, Z = x, y, 1.0 - x - y

    r = X * 3.2406 - Y * 1.5372 - Z * 0.4986
    g = -X * 0.9689 + Y * 1.8758 + Z * 0.0415
    b = X * 0.0557 - Y * 0.2040 + Z * 1.0570

    def correct_gamma(value: float) -> float:
        return 12.92 * value if value <= 0.0031308 else (1.0 + 0.055) * pow(value, 1.0 / 2.4) - 0.055

    r, g, b = map(correct_gamma, [r, g, b])

    max_val = max(r, g, b)
    if max_val > 1:
        r, g, b = [color / max_val for color in [r, g, b]]

    r, g, b = [max(0, color) for color in [r, g, b]]
    return clampRGB([r * bri, g * bri, b * bri])

def hsv_to_rgb(h: int, s: int, v: int) -> List[int]:
    """
    Convert HSV values to RGB color space.

    Args:
        h: Hue value.
        s: Saturation value.
        v: Value (brightness) value.

    Returns:
        List of RGB values [R, G, B].
    """
    s_norm, v_norm = s / 254, v / 254
    c = v_norm * s_norm
    x = c * (1 - abs((h / 11850) % 2 - 1))
    m = v_norm - c

    if h < 10992:
        r, g, b = c, x, 0
    elif h < 21845:
        r, g, b = x, c, 0
    elif h < 32837:
        r, g, b = 0, c, x
    elif h < 43830:
        r, g, b = 0, x, c
    elif h < 54813:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    return clampRGB([(r + m) * 255, (g + m) * 255, (b + m) * 255])
