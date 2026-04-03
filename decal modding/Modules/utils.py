import os
from PIL import Image

def strip_quotes(s):
    """Remove surrounding quotes and whitespace"""
    return s.strip().strip('"')

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'=' * 60}\n{title:^60}\n{'=' * 60}\n")

def print_menu_options(options):
    """Print formatted menu options"""
    print(f"\n{'-' * 60}")
    for opt in options:
        print(f"  {opt}")
    print(f"{'-' * 60}")

def get_base_name(filename):
    """Get base name without extension and 'out' suffix"""
    base = os.path.splitext(filename)[0]
    return base[:-3] if base.endswith('out') else base

def confirm_action(message="Proceed? (y/n): "):
    """Get user confirmation"""
    return input(message).strip().lower() == 'y'

def parse_dimensions(size_str):
    """Parse WIDTHxHEIGHT string, return (width, height) or None"""
    try:
        parts = size_str.lower().split('x')
        if len(parts) == 2:
            w, h = int(parts[0]), int(parts[1])
            if w > 0 and h > 0:
                return (w, h)
    except ValueError:
        pass
    return None

def read_image_dimensions(image_path):
    try:
        with Image.open(image_path) as img:
            return img.size  # (w, h)
    except Exception:
        return None

def is_alpha_mask(image_path):
    """Check if an image is an alpha mask by its color content"""
    try:
        img = Image.open(image_path).convert('RGB')
        w, h = img.size
        r, g, b = img.getpixel((w // 2, h // 2))[:3]
        return r < 50 and b > 200
    except:
        return False