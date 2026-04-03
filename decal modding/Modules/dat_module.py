import os
from Modules.utils import read_image_dimensions

def write_dat_format(dat_path, format_str):
    """Write texture format to a DAT metadata file"""
    try:
        with open(dat_path, 'r+b') as f:
            magic = f.read(13)
            
            # Remastered version check
            if magic in (b'\x00' * 12 + b'\x07', b'\x00' * 12 + b'\x09'):
                # Remastered - format at 0x2C
                f.seek(0x2C)
                if format_str == 'DXT5' or format_str == 'BC3_UNORM':
                    f.write(b'\x4D')  # DXT5
                elif format_str == 'DXT1' or format_str == 'BC1_UNORM':
                    f.write(b'\x47')  # DXT1
            elif magic[:9] == b'\x00' * 8 + b'\x01':
                # Original - format at 0xC
                f.seek(0xC)
                if format_str == 'DXT5' or format_str == 'BC3_UNORM':
                    f.write(b'DXT5')
                elif format_str == 'DXT1' or format_str == 'BC1_UNORM':
                    f.write(b'DXT1')
        
        print(f"       Updated format in metadata DAT to {format_str}")
        return True
    except Exception as e:
        print(f"       Error updating format: {e}")
        return False

def read_dat_dimensions(dat_path):
    """Read width and height from a DAT metadata file"""
    with open(dat_path, 'rb') as f:
        magic = f.read(13)
        
        # Remastered version check
        if magic in (b'\x00' * 12 + b'\x07', b'\x00' * 12 + b'\x09'):
            f.seek(0x34)
        else:
            f.seek(0x10)
        
        w = int.from_bytes(f.read(2), 'little')
        h = int.from_bytes(f.read(2), 'little')
    
    return w, h

def write_dat_dimensions(dat_path, width, height):
    """Write new width and height to a DAT metadata file"""
    try:
        with open(dat_path, 'r+b') as f:
            magic = f.read(13)
            
            # Remastered version check
            offset = 0x34 if magic in (b'\x00' * 12 + b'\x07', b'\x00' * 12 + b'\x09') else 0x10
            
            f.seek(offset)
            f.write(width.to_bytes(2, 'little'))
            f.write(height.to_bytes(2, 'little'))
        
        print(f"       Updated: {dat_path}")
        return True
    except Exception as e:
        print(f"       Error: {e}")
        return False

def warn_if_dimension_mismatch(image_path, dat_path):
    warnings = []

    img_dims = read_image_dimensions(image_path)
    if not img_dims:
        warnings.append("Could not read image dimensions")
        return warnings

    img_w, img_h = img_dims

    if os.path.exists(dat_path):
        try:
            dat_w, dat_h = read_dat_dimensions(dat_path)

            if (img_w, img_h) != (dat_w, dat_h):
                warnings.append(
                    f"Dimension mismatch: Image {img_w}x{img_h} != DAT {dat_w}x{dat_h}"
                )

            if (dat_w, dat_h) == (128, 128) and (img_w, img_h) != (128, 128):
                warnings.append(
                    "DAT is marked as icon (128x128) but image is not"
                )

        except Exception:
            warnings.append("Could not read DAT metadata")

    return warnings