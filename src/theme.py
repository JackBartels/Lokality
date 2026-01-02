"""
Theme configuration for Lokality.
Defines colors and fonts used throughout the GUI.
"""
import sys

class Theme:
    """
    Defines the visual style of the application.
    """
    # --- COLORS ---
    BG_COLOR = "#212121"       # Dark Grey
    FG_COLOR = "#ECECEC"       # Off-white
    ACCENT_COLOR = "#6B728E"   # Cooler Blue-Purple (Top border)
    COMMAND_COLOR = "#8B93B5"  # More Blue-toned Purple (Bottom border)
    SLASH_COLOR = "#B3E5FC"    # Brighter version of user blue
    INPUT_BG = "#303030"       # Slightly lighter grey for inputs
    BUTTON_FG = "#FFFFFF"

    # Message separators
    SEPARATOR_COLOR = "#2A2A2A"

    # Tags Colors
    USER_COLOR = "#90CAF9"
    SYSTEM_COLOR = "#B0BEC5"
    ERROR_COLOR = "#EF9A9A"
    CANCELLED_COLOR = "#B05555"
    LINK_COLOR = "#64B5F6"

    # Markdown specific
    CODE_BG = "#2D2D2D"
    CODE_FG = "#F8F8F2"
    TABLE_BG = "#282828"
    TOOLTIP_BG = "#37474F"

    @classmethod
    def get_fonts(cls):
        """Returns a dictionary of font definitions."""
        base_family = "Roboto"
        code_family = "Consolas" if sys.platform == "win32" else "Monospace"

        return {
            "base": (base_family, 11),
            "bold": (base_family, 11, "bold"),
            "italic": (base_family, 11, "italic"),
            "bold_italic": (base_family, 11, "bold italic"),
            "small": (base_family, 11, "italic"),
            "small_base": (base_family, 8),
            "code": (code_family, 10),
            "h1": (base_family, 20, "bold"),
            "h2": (base_family, 17, "bold"),
            "h3": (base_family, 14, "bold"),
            "unit": (base_family, 9, "bold"),
            "tooltip": (base_family, 9)
        }

    @staticmethod
    def get_color(name):
        """Returns a color value by name."""
        return getattr(Theme, name, None)
