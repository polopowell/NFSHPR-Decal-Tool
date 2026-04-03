import os
import numpy as np
from PIL import Image
from Modules.dds_module import save_image_dds

def generate_alpha_mask(input_path, output_dir=None, target_size=None, texconv_path="texconv.exe"):
    """Generate an alpha mask by converting alpha channel to blue/cyan"""
    img = Image.open(input_path).convert('RGBA')
    original_size = img.size
    alpha = np.array(img, dtype=np.uint8)[:, :, 3]
    
    if target_size:
        final_size = target_size
        alpha = np.array(Image.fromarray(alpha, mode='L').resize(target_size, Image.LANCZOS))
    else:
        final_size = original_size
    
    h, w = alpha.shape
    
    print(f"      Alpha mask will be: {w}x{h} pixels")
    
    output_data = np.zeros((h, w, 3), dtype=np.uint8)
    output_data[:, :, 0] = 0      # Red = 0
    output_data[:, :, 1] = alpha  # Green = alpha
    output_data[:, :, 2] = 255    # Blue = 255
    
    result = Image.fromarray(output_data, 'RGB')
    output_dir = output_dir or os.path.dirname(input_path)
    
    filename = os.path.basename(input_path)
    name, ext = os.path.splitext(filename)
    
    print(f"      Saving alpha mask as DDS with DXT5 compression...")
    
    # Always save as DDS with BC3_UNORM (DXT5)
    output_path = save_image_dds(result, output_dir, name, '_alpha', 'BC3_UNORM', texconv_path)
    
    if output_path and os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        
        block_width = max(1, w // 4)
        block_height = max(1, h // 4)
        expected_data_size = block_width * block_height * 16
        expected_total_size = 128 + expected_data_size
        
        print(f"      Output file size: {file_size:,} bytes ({file_size/1024:.2f} KB)")
        print(f"      Expected size: {expected_total_size:,} bytes ({expected_total_size/1024:.2f} KB)")
        
        if abs(file_size - expected_total_size) > 1000:
            print(f"      WARNING: File size mismatch! Check texconv output.")
        else:
            print(f"      ✓ File size is correct!")
    
    return output_path, name

def generate_icon(input_path, output_dir=None, texconv_path="texconv.exe"):
    """Generate a 128x128 icon from an image"""
    img = Image.open(input_path)
    icon = img.resize((128, 128), Image.LANCZOS).convert('RGBA')
    
    output_dir = output_dir or os.path.dirname(input_path)
    name, ext = os.path.splitext(os.path.basename(input_path))
    
    # Always save icons as DDS
    output_path = save_image_dds(icon, output_dir, name, '_icon', 'BC3_UNORM', texconv_path)
    
    return output_path, name