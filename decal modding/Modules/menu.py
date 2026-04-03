import os
from PIL import Image
from Modules.config import save_config, DEFAULT_CONFIG
from Modules.utils import strip_quotes, print_section, print_menu_options, confirm_action, parse_dimensions, is_alpha_mask, get_base_name, read_image_dimensions
from Modules.image_gen import generate_alpha_mask, generate_icon
from Modules.dat_module import read_dat_dimensions, write_dat_dimensions, warn_if_dimension_mismatch
from Modules.image_conv import convert_image_to_dat

def auto_convert_decal_menu(locator, config):
    print_section("AUTO CONVERT DECAL")
    
    image_path = strip_quotes(input("Enter image file: "))
    if not os.path.exists(image_path):
        print(f"\nError: File '{image_path}' not found!\n")
        return
    
    decal_name = input("Enter decal name (eg. TEX_1273719_1273720_DL): ").strip()
    
    # Find ALL files in the bundle
    bundle_files = [(img, info) for img, info in locator.texture_map.items() 
                   if info['bundle'] == decal_name]
    
    if not bundle_files:
        print(f"\nError: Bundle '{decal_name}' not found in index.\n")
        return
    
    # Separate files by type
    main_texture_info = None
    alpha_mask_info = None
    icon_info = None
    
    for img_name, info in bundle_files:
        img_dims = read_image_dimensions(info['image_path'])
        
        # Check if it's an icon (128x128)
        if img_dims and img_dims == (128, 128):
            icon_info = (img_name, info)
        # Check if it's an alpha mask
        elif is_alpha_mask(info['image_path']):
            alpha_mask_info = (img_name, info)
        # Otherwise it's the main texture
        else:
            main_texture_info = (img_name, info)
    
    # Use the main texture info
    if not main_texture_info:
        print(f"\nError: Could not find main texture in bundle '{decal_name}'")
        print(f"Found files:")
        for img_name, info in bundle_files:
            img_dims = read_image_dimensions(info['image_path'])
            file_type = "Icon (128x128)" if img_dims == (128, 128) else ("Alpha Mask" if is_alpha_mask(info['image_path']) else "Unknown")
            print(f"  - {img_name} ({file_type})")
        print()
        return
    
    decal_info = main_texture_info[1]
    
    print(f"\nFound main texture: {main_texture_info[0]}")
    print(f"Bundle: {decal_info['bundle']}")
    if alpha_mask_info:
        print(f"Alpha mask: {alpha_mask_info[0]}")
    if icon_info:
        print(f"Icon: {icon_info[0]}")
    
    try:
        img = Image.open(image_path)
        img_w, img_h = img.size
        
        # Consistent check for multiple-of-4 to match conversion script
        if img_w % 4 != 0 or img_h % 4 != 0:
            new_w = (img_w + 3) // 4 * 4
            new_h = (img_h + 3) // 4 * 4
            print(f"\nCorrection: Image dimensions {img_w}x{img_h} will be resized to {new_w}x{new_h}")
            print(f"(Required for texture block alignment)")
            img_w, img_h = new_w, new_h
        has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
        img.close()
        
        print(f"\nImage size: {img_w}x{img_h}")
        
        warnings = []
        if not has_alpha:
            warnings.append("Image has no transparency - decal will be fully opaque")
        
        if warnings:
            print("\nWARNINGS:")
            for w in warnings:
                print(f"  - {w}")
            
            if not confirm_action("\nContinue? (y/n): "):
                print("\nCancelled.\n")
                return
        
        dat_w, dat_h = read_dat_dimensions(decal_info['dat_path'])
        print(f"\nCurrent decal dimensions: {dat_w}x{dat_h}")
        
        need_dimension_change = (img_w, img_h) != (dat_w, dat_h)
        
        if need_dimension_change:
            print(f"Dimension mismatch detected: Image {img_w}x{img_h} != Decal {dat_w}x{dat_h}")
            
            if confirm_action("Update decal dimensions to match image? (y/n): "):
                print(f"\nUpdating decal dimensions to {img_w}x{img_h}")
                if not write_dat_dimensions(decal_info['dat_path'], img_w, img_h):
                    print("Warning: Failed to update dimensions")
            else:
                print("\nWarning: Dimension mismatch will remain - this may cause issues")
                if not confirm_action("Continue anyway? (y/n): "):
                    print("\nCancelled.\n")
                    return
        else:
            print(f"Image dimensions match decal metadata ({img_w}x{img_h})")
        
        # Handle alpha mask regeneration
        if alpha_mask_info:
            alpha_mask_name, alpha_info = alpha_mask_info
            print(f"\nFound alpha mask: {alpha_mask_name}")
            
            if confirm_action("Regenerate alpha mask from new image? (y/n): "):
                print(f"\nRegenerating alpha mask...")
                
                target_size = (img_w, img_h)
                output_path, _ = generate_alpha_mask(
                    image_path, 
                    os.path.dirname(alpha_info['image_path']), 
                    target_size, 
                    config['texconv_path']
                )
                
                # Replace the old alpha mask
                os.replace(output_path, alpha_info['image_path'])
                print("Alpha mask replaced successfully")
                
                # Update alpha mask dimensions
                alpha_curr_w, alpha_curr_h = read_dat_dimensions(alpha_info['dat_path'])
                if (alpha_curr_w, alpha_curr_h) != (img_w, img_h):
                    print(f"Updating alpha mask metadata: {alpha_curr_w}x{alpha_curr_h} -> {img_w}x{img_h}")
                    write_dat_dimensions(alpha_info['dat_path'], img_w, img_h)
            else:
                print("Skipping alpha mask regeneration")
                alpha_mask_info = None  # Don't convert it later
        else:
            print(f"\nNo alpha mask found in bundle")
            alpha_mask_info = None
        
        # Convert main texture
        print("\n" + "="*60)
        print("CONVERTING MAIN TEXTURE")
        print("="*60)
        
        main_texture_dat = os.path.join(
            os.path.dirname(decal_info['dat_path']), 
            f"{decal_info['base_name']}_texture.dat"
        )
        
        print(f"\nConverting: {os.path.basename(image_path)}")
        print(f"Target: {main_texture_dat}")
        
        if not convert_image_to_dat(image_path, main_texture_dat, config['texconv_path']):
            print("\n✗ Error: Failed to convert main texture")
            return
        
        print("\n✓ Main texture converted successfully")
        
        # Convert alpha mask if it was regenerated
        if alpha_mask_info:
            alpha_mask_name, alpha_info = alpha_mask_info
            
            print("\n" + "="*60)
            print("CONVERTING ALPHA MASK")
            print("="*60)
            
            alpha_dat = os.path.join(
                os.path.dirname(alpha_info['dat_path']), 
                f"{alpha_info['base_name']}_texture.dat"
            )
            
            print(f"\nConverting: {alpha_mask_name}")
            print(f"Target: {alpha_dat}")
            
            if not convert_image_to_dat(alpha_info['image_path'], alpha_dat, config['texconv_path']):
                print("\n⚠ Warning: Failed to convert alpha mask")
            else:
                print("\n✓ Alpha mask converted successfully")
        
        print(f"\n{'=' * 60}")
        print("AUTO CONVERSION COMPLETE")
        print(f"{'=' * 60}")
        print(f"Bundle: {decal_name}")
        print(f"Main texture: {main_texture_info[0]}")
        print(f"Dimensions: {img_w}x{img_h}")
        print(f"Alpha mask: {'Regenerated and converted' if alpha_mask_info else 'Not found'}")
        print(f"{'=' * 60}\n")
        
    except Exception as e:
        print(f"\nError during auto conversion: {e}\n")
        import traceback
        traceback.print_exc()

def setup_directories_menu(config):
    print_section("DIRECTORY SETUP")
    
    print("Current configuration:")
    print(f"  Images Directory: {config['images_dir']}")
    print(f"  Raw Directory:    {config['raw_dir']}")
    print(f"  Texconv Path:     {config['texconv_path']}")
    
    print("\nWhat would you like to configure?")
    print_menu_options([
        "[1] Images Directory (where exported textures are stored)",
        "[2] Raw Directory (where .DAT files are located)",
        "[3] Texconv Path (path to texconv.exe)",
        "[4] Reset to defaults",
        "[5] Back to main menu"
    ])
    
    choice = input("\nChoice: ").strip()
    
    if choice == '1':
        new_path = strip_quotes(input("\nEnter Images Directory path: "))
        if new_path:
            config['images_dir'] = new_path
            print(f"\nImages Directory set to: {new_path}")
            save_config(config)
    
    elif choice == '2':
        new_path = strip_quotes(input("\nEnter Raw Directory path: "))
        if new_path:
            config['raw_dir'] = new_path
            print(f"\nRaw Directory set to: {new_path}")
            save_config(config)
    
    elif choice == '3':
        new_path = strip_quotes(input("\nEnter Texconv path (e.g., C:/Tools/texconv.exe): "))
        if new_path:
            config['texconv_path'] = new_path
            print(f"\nTexconv path set to: {new_path}")
            save_config(config)
    
    elif choice == '4':
        if confirm_action("Reset all settings to defaults? (y/n): "):
            config.update(DEFAULT_CONFIG)
            save_config(config)
            print("\nConfiguration reset to defaults!")
    
    elif choice == '5':
        return
    
    else:
        print("\nInvalid choice.\n")

def icon_generator_menu(config):
    print_section("ICON GENERATOR (128x128)")
    
    input_file = strip_quotes(input("Enter File: "))
    if not os.path.exists(input_file):
        print(f"\nError: File '{input_file}' not found!\n")
        return
    
    try:
        img = Image.open(input_file)
        w, h = img.size
        img.close()
        print(f"\nOriginal size: {w}x{h}\nIcon will be resized to: 128x128")
    except Exception as e:
        print(f"\nError reading image: {e}\n")
        return
    
    output_dir = strip_quotes(input("\nEnter Output Directory (Leave empty for same directory): "))
    if output_dir and not os.path.exists(output_dir):
        print(f"\nError: Directory '{output_dir}' not found!\n")
        return
    
    try:
        output_path, filename = generate_icon(input_file, output_dir, config['texconv_path'])
        print(f"\nGenerated Icon for {filename}.\nSaved to: {output_path}\n")
    except Exception as e:
        print(f"\nError generating icon: {e}\n")

def alpha_mask_menu(config):
    print_section("ALPHA MASK GENERATOR")
    
    input_file = strip_quotes(input("Enter File: "))
    if not os.path.exists(input_file):
        print(f"\nError: File '{input_file}' not found!\n")
        return
    
    try:
        w, h = Image.open(input_file).size
        print(f"\nOriginal size: {w}x{h}")
    except:
        pass
    
    custom_size = input("\nEnter custom size (WIDTHxHEIGHT | e.g., 1024x1024) or leave empty to keep original: ").strip()
    target_size = parse_dimensions(custom_size)
    
    if target_size:
        print(f"Target size set to: {target_size[0]}x{target_size[1]}")
    
    output_dir = strip_quotes(input("\nEnter Output Directory (Leave empty for same directory): "))
    if output_dir and not os.path.exists(output_dir):
        print(f"\nError: Directory '{output_dir}' not found!\n")
        return
    
    try:
        output_path, filename = generate_alpha_mask(input_file, output_dir, target_size, config['texconv_path'])
        print(f"\nGenerated Alpha Mask for {filename}.")
        if target_size:
            print(f"Resized to: {target_size[0]}x{target_size[1]}")
        print(f"Saved to: {output_path}\n")
    except Exception as e:
        print(f"\nError generating alpha mask: {e}\n")

def regenerate_alpha_mask_menu(config):
    print_section("REGENERATE ALPHA MASK")
    
    input_file = strip_quotes(input("Enter Source Image File: "))
    if not os.path.exists(input_file):
        print(f"\nError: File '{input_file}' not found!\n")
        return
    
    if is_alpha_mask(input_file):
        print(f"\nError: This file is already an alpha mask!\n")
        return
    
    try:
        w, h = Image.open(input_file).size
        print(f"\nSource image size: {w}x{h}")
    except:
        pass
    
    alpha_mask_file = strip_quotes(input("\nEnter Alpha Mask File to Replace: "))
    if not os.path.exists(alpha_mask_file):
        print(f"\nError: Alpha mask file '{alpha_mask_file}' not found!\n")
        return
    
    try:
        alpha_w, alpha_h = Image.open(alpha_mask_file).size
        print(f"Alpha mask size: {alpha_w}x{alpha_h}")
    except:
        pass
    
    if not is_alpha_mask(alpha_mask_file):
        print(f"\nWarning: The specified file doesn't appear to be an alpha mask.")
        if not confirm_action("Continue anyway? (y/n): "):
            print("\nCancelled.\n")
            return
    
    custom_size = input("\nEnter custom size (WIDTHxHEIGHT | eg. 1024x1024) or leave empty to keep original: ").strip()
    target_size = parse_dimensions(custom_size)
    
    if target_size:
        print(f"Target size set to: {target_size[0]}x{target_size[1]}")
    
    try:
        output_path, filename = generate_alpha_mask(input_file, os.path.dirname(input_file), target_size, config['texconv_path'])
        os.replace(output_path, alpha_mask_file)
        
        print(f"\nRegenerated Alpha Mask for {filename}.")
        if target_size:
            print(f"Resized to: {target_size[0]}x{target_size[1]}")
        print(f"Replaced: {alpha_mask_file}\n")
    except Exception as e:
        print(f"\nError regenerating alpha mask: {e}\n")

def decal_locator_menu(locator):
    while True:
        print_section("DECAL LOCATOR")
        print_menu_options([
            "[1] Find .DAT file for an image",
            "[2] Search decals",
            "[3] Rebuild index",
            "[4] Back to main menu"
        ])
        
        choice = input("\nChoice: ").strip()
        
        if choice == '1':
            image_name = input("\nEnter image filename: ").strip()
            result = locator.find_dat(image_name)
            
            if result:
                print(f"\n{'=' * 60}\n  DECAL FOUND\n{'=' * 60}")
                print(f"\n  Image:  {result['image_path']}")
                print(f"  DAT:    {result['dat_path']}")
                print(f"  Bundle: {result['bundle']}\n")
            else:
                print(f"\nCould not find .DAT file for '{image_name}'\n")
        
        elif choice == '2':
            query = input("\nEnter search query: ").strip()
            results = locator.search(query)
            
            if results:
                print(f"\n{'=' * 60}\n  {len(results)} RESULT(S) FOUND\n{'=' * 60}\n")
                for i, (img, info) in enumerate(results, 1):
                    print(f"  [{i}] {img}")
                    print(f"      DAT: {info['dat_path']}")
                    print(f"      Bundle: {info['bundle']}\n")
            else:
                print(f"\nNo results found for '{query}'\n")
        
        elif choice == '3':
            locator.build_index()
        
        elif choice == '4':
            break
        
        else:
            print("\nInvalid choice. Please enter 1-4.\n")

def change_decal_dimensions_menu(locator):
    print_section("CHANGE DECAL DIMENSIONS")
    
    if not locator.texture_map:
        print("Error: No texture mappings found. Please rebuild index first.\n")
        return
    
    print_menu_options([
        "[1] Single File - Change dimensions for a specific file",
        "[2] Bundle - Change dimensions for all files in a bundle",
        "[3] Cancel"
    ])
    
    choice = input("\nChoice: ").strip()
    
    if choice == '3':
        print("\nCancelled.\n")
        return
    
    if choice == '1':
        print(f"\n{'-' * 60}\nEnter image filename OR bundle name + filename\n"
              f"Examples:\n  - 8A_EA_7D_70out.dds\n  - TEX_1273701_1273702_DL/8A_EA_7D_70out.dds\n{'-' * 60}")
        
        file_input = input("\nFile: ").strip()
        info = locator.find_dat(file_input)
        
        if not info and ('/' in file_input or '\\' in file_input):
            parts = file_input.replace('\\', '/').split('/')
            bundle_name = parts[0] if len(parts) > 1 else None
            filename = parts[-1]
            
            for img, img_info in locator.texture_map.items():
                if bundle_name and img_info['bundle'] != bundle_name:
                    continue
                if img.lower() == filename.lower() or img_info['base_name'].lower() == get_base_name(filename).lower():
                    info = img_info
                    break
        
        if not info or not os.path.exists(info['dat_path']):
            print(f"\nError: Could not find mapping for '{file_input}'\n")
            return
        
        try:
            curr_w, curr_h = read_dat_dimensions(info['dat_path'])
            
            if curr_w == 128 and curr_h == 128:
                print(f"\nError: Cannot change dimensions for icon files (128x128).\n")
                return
            
            print(f"\nCurrent dimensions: {curr_w}x{curr_h}")
        except Exception as e:
            print(f"\nError reading current dimensions: {e}\n")
            return
        
        new_size = input("\nEnter new dimensions (WIDTHxHEIGHT | eg. 2048x2048): ").strip()
        dims = parse_dimensions(new_size)
        
        if not dims:
            print("\nInvalid format. Use WIDTHxHEIGHT (eg. 2048x2048)\n")
            return
        
        new_w, new_h = dims
        print(f"\nChanging dimensions from {curr_w}x{curr_h} to {new_w}x{new_h}")
        print(f"File: {info['dat_path']}")
        
        if confirm_action():
            if write_dat_dimensions(info['dat_path'], new_w, new_h):
                print("\nDimensions changed successfully!\n")
            else:
                print("\nFailed to change dimensions.\n")
        else:
            print("\nCancelled.\n")
    
    elif choice == '2':
        print(f"\n{'-' * 60}\nEnter bundle name OR select from list\n{'-' * 60}")
        
        bundles = locator.get_bundles()
        if not bundles:
            print("\nNo bundles found.\n")
            return
        
        print(f"\nAvailable bundles ({len(bundles)}):\n")
        for i, bundle in enumerate(bundles, 1):
            count = sum(1 for info in locator.texture_map.values() if info['bundle'] == bundle)
            print(f"  [{i}] {bundle} ({count} files)")
        
        bundle_input = input("\nEnter bundle name or number: ").strip()
        selected = locator.select_bundle(bundle_input, bundles)
        
        if not selected:
            print(f"\nError: Bundle '{bundle_input}' not found.\n")
            return
        
        files = [(img, info) for img, info in locator.texture_map.items() if info['bundle'] == selected]
        
        icon_files = []
        valid_files = []
        
        for img, info in files:
            if not os.path.exists(info['dat_path']):
                continue
            
            img_dims = read_image_dimensions(info['image_path'])
            if img_dims and img_dims == (128, 128):
                icon_files.append(img)
            else:
                valid_files.append((img, info))
        
        print(f"\nBundle: {selected}")
        print(f"Files to modify: {len(valid_files)}")
        if icon_files:
            print(f"Icon files (will be skipped): {len(icon_files)}\n")
        else:
            print()
        
        new_size = input("Enter new dimensions (WIDTHxHEIGHT | eg. 2048x2048): ").strip()
        dims = parse_dimensions(new_size)
        
        if not dims:
            print("\nInvalid format. Use WIDTHxHEIGHT (e.g., 2048x2048)\n")
            return
        
        new_w, new_h = dims
        print(f"\nThis will change dimensions to {new_w}x{new_h} for all files in the bundle.")
        
        if not confirm_action():
            print("\nCancelled.\n")
            return
        
        changed, skipped, errors = 0, 0, 0
        
        for image_name, info in valid_files:
            try:
                curr_w, curr_h = read_dat_dimensions(info['dat_path'])
                print(f"Changing {image_name}: {curr_w}x{curr_h} -> {new_w}x{new_h}")
                
                if write_dat_dimensions(info['dat_path'], new_w, new_h):
                    changed += 1
                else:
                    errors += 1
            except Exception as e:
                print(f"  Error: {e}")
                errors += 1
        
        if icon_files:
            print(f"\nSkipped {len(icon_files)} icon files (128x128 images)")
        
        print(f"\n{'=' * 60}\nSUMMARY\n{'=' * 60}")
        print(f"Files changed: {changed}\nErrors: {errors}\n{'=' * 60}\n")
    
    else:
        print("\nInvalid choice.\n")

def convert_images_to_dat_menu(locator, config):
    print_section("CONVERT IMAGES TO DAT")

    if not locator.texture_map:
        print("Error: No texture mappings found. Please rebuild index first.\n")
        return

    print_menu_options([
        "[1] File - Convert a specific file",
        "[2] Bundle - Convert all files in a bundle",
        "[3] All Bundles - Convert every bundle",
        "[4] Cancel"
    ])

    choice = input("\nChoice: ").strip()

    if choice == '4':
        print("\nCancelled.\n")
        return

    if choice == '1':
        print(f"\n{'-' * 60}\nEnter image filename OR bundle name + filename\n"
              f"Examples:\n  - 8A_EA_7D_70out.dds\n"
              f"  - TEX_1273701_1273702_DL/8A_EA_7D_70out.dds\n{'-' * 60}")

        file_input = input("\nFile: ").strip()
        info = locator.find_dat(file_input)

        if not info and ('/' in file_input or '\\' in file_input):
            parts = file_input.replace('\\', '/').split('/')
            bundle_name = parts[0] if len(parts) > 1 else None
            filename = parts[-1]

            for img, img_info in locator.texture_map.items():
                if bundle_name and img_info['bundle'] != bundle_name:
                    continue
                if img.lower() == filename.lower() or \
                   img_info['base_name'].lower() == get_base_name(filename).lower():
                    info = img_info
                    break

        if not info or not os.path.exists(info['image_path']):
            print(f"\nError: Could not find mapping for '{file_input}'\n")
            return

        dat_dir = os.path.dirname(info['dat_path'])
        texture_dat = os.path.join(dat_dir, f"{info['base_name']}_texture.dat")

        file_type = "Alpha Mask" if is_alpha_mask(info['image_path']) else "Texture"

        print(f"\nFound: {os.path.basename(info['image_path'])} ({file_type})")
        print(f"Bundle: {info['bundle']}")
        print(f"\nConverting: {info['image_path']}")

        warnings = warn_if_dimension_mismatch(
            info['image_path'],
            info['dat_path']
        )

        if warnings:
            print("\nWARNINGS:")
            for w in warnings:
                print(f"  - {w}")

            if not confirm_action("Continue conversion anyway? (y/n): "):
                print("\nSkipped.\n")
                return

        if convert_image_to_dat(info['image_path'], texture_dat, config['texconv_path']):
            print("\nConversion successful!\n")
        else:
            print("\nConversion failed!\n")

    elif choice in ('2', '3'):
        if choice == '2':
            print(f"\n{'-' * 60}\nEnter bundle name OR select from list\n{'-' * 60}")

            bundles = locator.get_bundles()
            if not bundles:
                print("\nNo bundles found.\n")
                return

            print(f"\nAvailable bundles ({len(bundles)}):\n")
            for i, bundle in enumerate(bundles, 1):
                count = sum(1 for info in locator.texture_map.values()
                            if info['bundle'] == bundle)
                print(f"  [{i}] {bundle} ({count} images)")

            bundle_input = input("\nEnter bundle name or number: ").strip()
            selected = locator.select_bundle(bundle_input, bundles)

            if not selected:
                print(f"\nError: Bundle '{bundle_input}' not found.\n")
                return

            images_to_convert = [
                (img, info) for img, info in locator.texture_map.items()
                if info['bundle'] == selected
            ]
        else:
            print("\nThis will convert ALL images in EVERY bundle to their")
            print("corresponding _texture.dat files.")

            images_to_convert = list(locator.texture_map.items())

        if not confirm_action():
            print("\nCancelled.\n")
            return

        bundles_to_check = {}
        for image_name, info in images_to_convert:
            bundle = info['bundle']
            if bundle not in bundles_to_check:
                bundles_to_check[bundle] = {'texture': False, 'alpha': False, 'icon': False}
            
            img_dims = read_image_dimensions(info['image_path'])
            if img_dims and img_dims == (128, 128):
                bundles_to_check[bundle]['icon'] = True
            elif is_alpha_mask(info['image_path']):
                bundles_to_check[bundle]['alpha'] = True
            else:
                bundles_to_check[bundle]['texture'] = True

        # Check for missing textures
        missing_texture_bundles = [b for b, files in bundles_to_check.items() 
                                   if not files['texture'] and (files['alpha'] or files['icon'])]

        if missing_texture_bundles:
            print(f"\n{'!' * 60}")
            print("WARNING: Missing main textures detected!")
            print(f"{'!' * 60}")
            print(f"\nThe following bundles are missing main decal textures:")
            for bundle in missing_texture_bundles:
                print(f"  - {bundle}")
            
            print(f"\nAttempting to rebuild index to find missing textures...")
            
            # Rebuild index
            old_count = len(locator.texture_map)
            locator.build_index()
            new_count = len(locator.texture_map)
            
            print(f"\nIndex rebuilt: {old_count} → {new_count} mappings")
            
            # Re-check after rebuild
            images_to_convert = list(locator.texture_map.items()) if choice == '3' else [
                (img, info) for img, info in locator.texture_map.items()
                if info['bundle'] == selected
            ]
            
            bundles_to_check = {}
            for image_name, info in images_to_convert:
                bundle = info['bundle']
                if bundle not in bundles_to_check:
                    bundles_to_check[bundle] = {'texture': False, 'alpha': False, 'icon': False}
                
                img_dims = read_image_dimensions(info['image_path'])
                if img_dims and img_dims == (128, 128):
                    bundles_to_check[bundle]['icon'] = True
                elif is_alpha_mask(info['image_path']):
                    bundles_to_check[bundle]['alpha'] = True
                else:
                    bundles_to_check[bundle]['texture'] = True
            
            still_missing = [b for b, files in bundles_to_check.items() 
                           if not files['texture'] and (files['alpha'] or files['icon'])]
            
            if still_missing:
                print(f"\n{'!' * 60}")
                print("ERROR: Main textures still missing after rebuild!")
                print(f"{'!' * 60}")
                print(f"\nThe following bundles still have missing textures:")
                for bundle in still_missing:
                    print(f"  - {bundle}")
                
                print(f"\nPossible causes:")
                print(f"  1. Main texture files don't exist in Images folder")
                print(f"  2. Main texture files don't have matching .dat files in Raw folder")
                print(f"  3. Files are named incorrectly")
                
                print(f"\nPlease check your Images and Raw folders manually.")
                print(f"Make sure each bundle has:")
                print(f"  - Main texture (e.g., 8A_EA_7D_70out.dds) - NOT 128x128")
                print(f"  - Alpha mask (cyan/blue image)")
                print(f"  - Icon (128x128 image)")
                
                if not confirm_action("\nContinue anyway (will skip missing textures)? (y/n): "):
                    print("\nCancelled.\n")
                    return
            else:
                print(f"\n✓ All textures found after rebuild!")

        converted, skipped, errors = 0, 0, 0

        for image_name, info in images_to_convert:
            if not os.path.exists(info['image_path']):
                print(f"\nSkipping missing file: {image_name}")
                skipped += 1
                continue

            # Check if this is an icon (128x128) - skip it
            img_dims = read_image_dimensions(info['image_path'])
            if img_dims and img_dims == (128, 128):
                print(f"\nSkipping icon: {image_name} (128x128)")
                skipped += 1
                continue

            dat_dir = os.path.dirname(info['dat_path'])
            texture_dat = os.path.join(dat_dir, f"{info['base_name']}_texture.dat")

            file_type = "Alpha" if is_alpha_mask(info['image_path']) else "Texture"
            print(f"\nConverting [{file_type}]: {image_name}")

            warnings = warn_if_dimension_mismatch(
                info['image_path'],
                info['dat_path']
            )

            if warnings:
                print("  WARNINGS:")
                for w in warnings:
                    print(f"    - {w}")

            if convert_image_to_dat(info['image_path'], texture_dat, config['texconv_path']):
                converted += 1
            else:
                errors += 1

        print(f"\n{'=' * 60}\nSUMMARY\n{'=' * 60}")
        print(f"Images converted: {converted}")
        print(f"Images skipped:   {skipped}")
        print(f"Errors:           {errors}")
        print(f"{'=' * 60}\n")

    else:
        print("\nInvalid choice.\n")