import os
import subprocess

def run_texconv(input_path, output_dir, format_type, output_name, texconv_path):
    """Run texconv.exe to convert image to DDS"""
    if not os.path.isabs(texconv_path) and not os.path.dirname(texconv_path):
        texconv_path = os.path.abspath(texconv_path)
    
    if not os.path.exists(texconv_path):
        print(f"      Warning: texconv not found at {texconv_path}")
        return None
    
    try:
        cmd = [
            texconv_path,
            "-f", format_type,
            "-m", "1",           # Only 1 mip level (no mipmaps)
            "-o", output_dir,
            "-y",                # Overwrite existing
            input_path
        ]
        
        print(f"      Running texconv: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        temp_output = os.path.join(output_dir, os.path.basename(input_path).replace('.png', '.dds'))
        final_output = os.path.join(output_dir, output_name)
        
        if os.path.exists(temp_output):
            file_size = os.path.getsize(temp_output)
            print(f"      Generated DDS: {file_size:,} bytes")
            
            if os.path.exists(final_output):
                os.remove(final_output)
            os.rename(temp_output, final_output)
            return final_output
        else:
            print(f"      Error: texconv did not create output file at {temp_output}")
            return None
            
    except subprocess.CalledProcessError as e:
        print(f"      Error with texconv: {e}")
        if e.stderr:
            print(f"      texconv stderr: {e.stderr}")
        return None
    except FileNotFoundError as e:
        print(f"      Error: texconv not found: {e}")
        return None

def save_image_dds(img, output_dir, base_name, suffix, format_type, texconv_path):
    """Save image as DDS with texconv or fallback to PNG"""
    temp_png = os.path.join(output_dir, f"{base_name}{suffix}_temp.png")
    output_dds = os.path.join(output_dir, f"{base_name}{suffix}.dds")
    
    img.save(temp_png, format='PNG', compress_level=0)
    
    print(f"      Saved temp PNG: {os.path.getsize(temp_png):,} bytes")
    
    result = run_texconv(temp_png, output_dir, format_type, f"{base_name}{suffix}.dds", texconv_path)
    
    if result:
        print(f"      DDS saved with {format_type} compression")
        
        # Clean up temp PNG
        if os.path.exists(temp_png):
            try:
                os.remove(temp_png)
            except:
                pass
        return result
    
    print(f"      Fallback: keeping temp PNG (texconv failed)")
    fallback_name = os.path.join(output_dir, f"{base_name}{suffix}.png")
    if os.path.exists(fallback_name):
        os.remove(fallback_name)
    os.rename(temp_png, fallback_name)
    return fallback_name

def get_dds_format_info(dds_path):
    """Read DDS format information from header"""
    try:
        with open(dds_path, 'rb') as f:
            # Read magic
            magic = f.read(4)
            if magic != b'DDS ':
                return None, None
            
            # Skip header size
            f.read(4)
            
            # Skip flags, height, width
            f.seek(0x14, 0)
            
            # Read pitchOrLinearSize
            pitch = int.from_bytes(f.read(4), 'little')
            
            # Jump to pixel format
            f.seek(0x54, 0)
            fourcc = f.read(4)
            
            format_name = fourcc.decode('ascii', errors='ignore') if len(fourcc) == 4 else 'Unknown'
            
            return format_name, pitch
    except Exception as e:
        print(f"Error reading DDS header: {e}")
        return None, None

def get_dds_compression_data(dds_path):
    """Extract raw compressed texture data from DDS file"""
    try:
        with open(dds_path, 'rb') as f:
            # DDS header is always 128 bytes (0x80)
            # Skip to texture data
            f.seek(0x80)
            data = f.read()
            
            # Debug info
            format_name, pitch = get_dds_format_info(dds_path)
            if format_name:
                print(f"       DDS Format: {format_name}, Data size: {len(data)} bytes")
            
            return data
    except Exception as e:
        print(f"Error reading DDS: {e}")
        return None