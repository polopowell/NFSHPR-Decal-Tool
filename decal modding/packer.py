import os
import json
import struct
import zlib
import math

def load_index():
    """Load the decal index"""
    if not os.path.exists("decal_index.json"):
        print("\nError: decal_index.json not found!")
        print("Building index now...")
        
        try:
            from decal_tool import DecalLocator
            locator = DecalLocator()
            locator.build_index()
            
            with open("decal_index.json", 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"\nCould not build index: {e}")
            print("Please run the main NFS:HPR Decal Modding Tool first to build the index.")
            return None
    
    with open("decal_index.json", 'r') as f:
        return json.load(f)

def find_bundle_by_name(bundle_name, raw_dir="Raw"):
    """Find bundle folder by name"""
    bundle_path = os.path.join(raw_dir, bundle_name)
    if os.path.exists(bundle_path):
        return bundle_path
    return None

def find_bundle_by_decal_id(decal_id, texture_map):
    """Find bundle by decal ID (e.g., 8A_EA_7D_70)"""
    for image_name, info in texture_map.items():
        if decal_id.upper() in info['base_name'].upper():
            return info['bundle']
    return None

def find_ids_file(bundle_folder):
    """Find IDs.BIN or IDs_*.BIN in bundle folder"""
    bundle_name = os.path.basename(bundle_folder)
    
    # Try IDs_bundlename.BIN first
    ids_path = os.path.join(bundle_folder, f"IDs_{bundle_name}.BIN")
    if os.path.exists(ids_path):
        return ids_path
    
    # Try IDs.BIN
    ids_path = os.path.join(bundle_folder, "IDs.BIN")
    if os.path.exists(ids_path):
        return ids_path
    
    return None

def calculate_padding(length, alignment):
    """Calculate padding needed for alignment"""
    if alignment == 0:
        return 0
    mod = length % alignment
    if mod == 0:
        return 0
    return alignment - mod

def pack_bundle(bundle_folder, output_dir="Output"):
    """Pack bundle files into BIN format"""
    ids_file = find_ids_file(bundle_folder)
    
    if not ids_file:
        print(f"Error: Could not find IDs.BIN in {bundle_folder}")
        return False
    
    print(f"\nPacking bundle...")
    print(f"IDs file: {ids_file}")
    print(f"Bundle folder: {bundle_folder}")
    
    try:
        # Read IDs file header
        with open(ids_file, 'rb') as f:
            magic = f.read(4)
            if magic != b'bnd2':
                print("Error: Invalid IDs file format!")
                return False
            
            muVersion = struct.unpack('<I', f.read(4))[0]
            muPlatform = struct.unpack('<I', f.read(4))[0]
            
            if muPlatform != 0x1:
                print("Error: Bundle platform not supported. Select a PC file version.")
                return False
            
            muDebugDataOffset = struct.unpack('<I', f.read(4))[0]
            muResourceEntriesCount = struct.unpack('<I', f.read(4))[0]
            muResourceEntriesOffset = struct.unpack('<I', f.read(4))[0]
            mauResourceDataOffset = list(struct.unpack('<4I', f.read(16)))
            muFlags = struct.unpack('<I', f.read(4))[0]
            pad1 = struct.unpack('<I', f.read(4))[0]
            
            print(f"\nBundle Info:")
            print(f"  Version: {muVersion}")
            print(f"  Platform: {muPlatform}")
            print(f"  Number of files: {muResourceEntriesCount}")
            print(f"  Compression: 0x{muFlags:X}")
            
            # Read notes and debug data
            f.seek(0x30)
            if muDebugDataOffset < muResourceEntriesOffset:
                notes_data = f.read(muDebugDataOffset - f.tell())
                f.seek(muDebugDataOffset)
                debug_data = f.read(muResourceEntriesOffset - muDebugDataOffset)
                
                # Remove trailing zeros from debug data
                k = 0
                for l in range(len(debug_data), 0, -1):
                    if debug_data[l-1] != 0:
                        break
                    k += 1
                k -= 1
                if k > 0:
                    debug_data = debug_data[:-k]
            else:
                notes_data = f.read(muResourceEntriesOffset - f.tell())
                debug_data = b''
            
            # Check if debug data bit is set
            if (muFlags >> 3) & 1 == 0:
                debug_data = b''
            
            # Read file entries
            entries = []
            for i in range(muResourceEntriesCount):
                entry_pos = muResourceEntriesOffset + (i * 0x50)
                f.seek(entry_pos)
                
                mResourceId = f.read(4)
                countBlock, null = struct.unpack('<2B', f.read(2))
                count, isIdInteger = struct.unpack('<2B', f.read(2))
                
                f.seek(entry_pos + 0x44)
                muResourceTypeId = struct.unpack('<I', f.read(4))[0]
                
                f.seek(entry_pos + 0x4A)
                unused_muFlags = struct.unpack('<B', f.read(1))[0]
                muStreamIndex = struct.unpack('<B', f.read(1))[0]
                
                # Convert ID to string
                id_hex = ''.join(f'{b:02X}' for b in mResourceId)
                id_str = '_'.join([id_hex[i:i+2] for i in range(0, 8, 2)])
                
                # Get resource type string
                resource_type = get_resource_type_from_id(muResourceTypeId)
                
                entries.append({
                    'id': id_str,
                    'id_bytes': mResourceId,
                    'type': resource_type,
                    'type_id': muResourceTypeId,
                    'countBlock': countBlock,
                    'count': count,
                    'isIdInteger': isIdInteger,
                    'muStreamIndex': muStreamIndex
                })
        
        print(f"\nPacking {len(entries)} files...\n")
        
        # Prepare data blocks
        resources_data = b''
        resources_data_body = b''
        
        # Process each file
        mResources = []
        for i, entry in enumerate(entries):
            # Build filename
            mResourceId = entry['id']
            if entry['countBlock'] != 0:
                mResourceId += f"_{entry['countBlock']}"
                if entry['count'] != 0:
                    mResourceId += f"_{entry['count']}"
            elif entry['countBlock'] == 0 and entry['count'] != 0:
                mResourceId += f"_{entry['countBlock']}_{entry['count']}"
            
            # Find file
            resource_dir = os.path.join(bundle_folder, entry['type'])
            resource_path = os.path.join(resource_dir, mResourceId + ".dat")
            
            if not os.path.exists(resource_path):
                print(f"  [{i+1}/{len(entries)}] ERROR: Missing {mResourceId}.dat in {entry['type']}")
                return False
            
            print(f"  [{i+1}/{len(entries)}] Packing: {mResourceId}")
            
            # Read main file
            with open(resource_path, 'rb') as f:
                resource0_data = f.read()
            
            # Compress if needed
            if muFlags in (0x1, 0x7, 0x9, 0xF, 0x11, 0x19, 0x21, 0x27, 0x29, 0x2F):
                disk0_data = zlib.compress(resource0_data, 9)
            else:
                disk0_data = resource0_data
            
            padding = calculate_padding(len(disk0_data), 0x10)
            
            # Check for texture file
            resource_path_body = ""
            resource1_data = b''
            disk1_data = b''
            
            if entry['type'] == "Texture":
                resource_path_body = os.path.join(resource_dir, mResourceId + "_texture.dat")
                if os.path.exists(resource_path_body):
                    print(f"      + texture data")
                    with open(resource_path_body, 'rb') as f:
                        resource1_data = f.read()
                    
                    if muFlags in (0x1, 0x7, 0x9, 0xF, 0x11, 0x19, 0x21, 0x27, 0x29, 0x2F):
                        disk1_data = zlib.compress(resource1_data, 9)
                    else:
                        disk1_data = resource1_data
            
            # Store offsets before adding data
            disk_offset_0 = len(resources_data)
            disk_offset_1 = len(resources_data_body) if disk1_data else 0
            
            # Add to Block1
            resources_data += disk0_data
            resources_data += b'\x00' * padding
            
            # Add to Block2 if texture data exists
            if disk1_data:
                padding_disk1 = calculate_padding(len(disk1_data), 0x80)
                resources_data_body += disk1_data
                resources_data_body += b'\x00' * padding_disk1
            
            # Store resource info
            mResources.append({
                'entry': entry,
                'disk_offsets': [disk_offset_0, disk_offset_1, 0, 0],
                'uncompressed_sizes': [len(resource0_data), len(resource1_data), 0, 0],
                'disk_sizes': [len(disk0_data), len(disk1_data), 0, 0]
            })
        
        # Calculate final positions - DO NOT move debug data
        # In HPR, debug data stays between header and entries
        ids_table_size = muResourceEntriesOffset + muResourceEntriesCount * 0x50
        mauResourceDataOffset[0] = ids_table_size
        mauResourceDataOffset[1] = mauResourceDataOffset[0] + len(resources_data)
        
        padding_before_block2 = calculate_padding(mauResourceDataOffset[1], 0x80)
        mauResourceDataOffset[1] += padding_before_block2
        
        mauResourceDataOffset[2] = mauResourceDataOffset[1] + len(resources_data_body)
        padding2 = calculate_padding(mauResourceDataOffset[2], 0x80)
        
        # Block 3 points to same location as block 2 end
        mauResourceDataOffset[3] = mauResourceDataOffset[2]
        
        # Total file size is where block 3 points to
        total_file_size = mauResourceDataOffset[3]
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Write output to Output folder
        bundle_name = os.path.basename(bundle_folder)
        output_file = os.path.join(output_dir, f"{bundle_name}.BIN")
        
        print(f"\nWriting: {output_file}")
        
        with open(output_file, 'wb') as out:
            # Write header
            out.write(b'bnd2')
            out.write(struct.pack('<I', muVersion))
            out.write(struct.pack('<I', muPlatform))
            out.write(struct.pack('<I', muDebugDataOffset))
            out.write(struct.pack('<I', muResourceEntriesCount))
            out.write(struct.pack('<I', muResourceEntriesOffset))
            out.write(struct.pack('<4I', *mauResourceDataOffset))
            out.write(struct.pack('<I', muFlags))
            out.write(struct.pack('<I', pad1))
            
            out.write(notes_data)
            
            # Write debug data if it exists (between notes and entries)
            if len(debug_data) > 0:
                out.write(debug_data)
                out.write(b'\x00' * calculate_padding(len(debug_data), 0x10))
            
            # Write entries
            for res in mResources:
                entry = res['entry']
                nibbles = get_nibbles_for_type_hpr(entry['type_id'])
                
                mauUncompressedSizeAndAlignment = [
                    res['uncompressed_sizes'][i] + nibbles[i] for i in range(4)
                ]
                
                out.write(entry['id_bytes'])
                out.write(struct.pack('<B', entry['countBlock']))
                out.write(struct.pack('<B', 0))
                out.write(struct.pack('<B', entry['count']))
                out.write(struct.pack('<B', entry['isIdInteger']))
                out.write(struct.pack('<I', 0))  # muImportHash
                out.write(struct.pack('<I', 0))  # muImportHash2
                out.write(struct.pack('<4I', *mauUncompressedSizeAndAlignment))
                out.write(struct.pack('<4I', *res['disk_sizes']))
                out.write(struct.pack('<4I', *res['disk_offsets']))
                out.write(struct.pack('<I', 0))  # muImportOffset
                out.write(struct.pack('<I', entry['type_id']))
                out.write(struct.pack('<H', 0))  # muImportCount
                out.write(struct.pack('<B', 0))
                out.write(struct.pack('<B', entry['muStreamIndex']))
                out.write(struct.pack('<I', 0))
            
            # Write data blocks
            out.write(resources_data)
            out.write(b'\x00' * padding_before_block2)
            out.write(resources_data_body)
            out.write(b'\x00' * padding2)
        
        print(f"\n" + "=" * 60)
        print("PACKING COMPLETE")
        print("=" * 60)
        print(f"Files packed: {len(entries)}")
        print(f"Block1 size: {len(resources_data)} bytes")
        print(f"Block2 size: {len(resources_data_body)} bytes")
        print(f"Total size: {total_file_size} bytes")
        print(f"Output: {output_file}")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def get_resource_type_from_id(type_id):
    """Map resource type ID to folder name for HPR"""
    type_map = {
        0x00000001: 'Texture',
        0x00000002: 'Material',
        0x00000003: 'VertexDescriptor',
        0x00000004: 'VertexProgramState',
        0x00000005: 'Renderable',
        0x00000006: 'MaterialState',
        0x00000007: 'SamplerState',
        0x00000008: 'ShaderProgramBuffer'
    }
    return type_map.get(type_id, f"{type_id:08X}")

def get_nibbles_for_type_hpr(type_id):
    """Get nibbles (alignment values) for resource type"""
    nibble_map = {
        0x00000001: [0x30000000, 0x40000000, 0x0, 0x0],  # Texture
        0x00000002: [0x0, 0x0, 0x0, 0x0],                 # Material
        0x00000003: [0x30000000, 0x0, 0x0, 0x0],          # VertexDescriptor
        0x00000004: [0x30000000, 0x0, 0x0, 0x0],          # VertexProgramState
        0x00000005: [0x40000000, 0x40000000, 0x0, 0x0],   # Renderable
        0x00000006: [0x0, 0x0, 0x0, 0x0],                 # MaterialState
        0x00000007: [0x30000000, 0x0, 0x0, 0x0],          # SamplerState
        0x00000008: [0x40000000, 0x20000000, 0x0, 0x0]    # ShaderProgramBuffer
    }
    return nibble_map.get(type_id, [0x40000000, 0x0, 0x0, 0x0])

def main():
    print("\n" + "=" * 60)
    print("        NFS:HPR DECAL PACKER")
    print("=" * 60 + "\n")
    
    # Load index
    print("Loading decal index...")
    texture_map = load_index()
    if not texture_map:
        input("\nPress Enter to exit...")
        return
    
    # Get input
    decal_input = input("Enter Decal To Pack (Name or Bundle): ").strip()
    
    bundle_folder = None
    
    # Find bundle
    if decal_input.startswith("TEX_") or len(decal_input.split('_')) >= 3:
        bundle_folder = find_bundle_by_name(decal_input)
        if not bundle_folder:
            bundle_name = find_bundle_by_decal_id(decal_input, texture_map)
            if bundle_name:
                bundle_folder = find_bundle_by_name(bundle_name)
    else:
        bundle_name = find_bundle_by_decal_id(decal_input, texture_map)
        if bundle_name:
            bundle_folder = find_bundle_by_name(bundle_name)
    
    if not bundle_folder:
        print(f"\nError: Could not find bundle for '{decal_input}'")
        input("\nPress Enter to exit...")
        return
    
    print(f"\nFound bundle: {os.path.basename(bundle_folder)}")
    
    confirm = input("\nProceed with packing? (y/n): ").strip().lower()
    if confirm != 'y':
        print("\nCancelled.")
        input("\nPress Enter to exit...")
        return
    
    # Pack
    success = pack_bundle(bundle_folder)
    
    if not success:
        print("\n" + "=" * 60)
        print("  PACKING FAILED!")
        print("=" * 60)
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFatal error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    input("\nPress Enter to exit...")