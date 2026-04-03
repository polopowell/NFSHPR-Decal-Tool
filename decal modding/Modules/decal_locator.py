import os
import json
from Modules.utils import get_base_name

class DecalLocator:
    def __init__(self, images_dir="Images", raw_dir="Raw"):
        self.images_dir = images_dir
        self.raw_dir = raw_dir
        self.index_file = "decal_index.json"
        self.texture_map = {}
    
    def build_index(self):
        """Build an index mapping image names to their .DAT file locations"""
        print("\nBuilding decal index...")
        print(f"  Images Directory: {self.images_dir}")
        print(f"  Raw Directory:    {self.raw_dir}")
        
        if not os.path.exists(self.raw_dir):
            print(f"\nError: Raw directory '{self.raw_dir}' not found!")
            print("Please configure directories in the setup menu.\n")
            return 0
        
        dat_files = [
            {
                'base_name': get_base_name(f),
                'dat_path': os.path.join(r, f),
                'bundle': os.path.basename(os.path.dirname(os.path.dirname(os.path.join(r, f))))
            }
            for r, _, files in os.walk(self.raw_dir)
            for f in files if f.lower().endswith('.dat')
        ]
        
        image_files = []
        if os.path.exists(self.images_dir):
            image_files = [
                {
                    'original_name': f,
                    'base_name': get_base_name(f),
                    'image_path': os.path.join(r, f)
                }
                for r, _, files in os.walk(self.images_dir)
                for f in files if f.lower().endswith(('.dds', '.png', '.jpg', '.tga'))
            ]
        else:
            print(f"\nWarning: Images directory '{self.images_dir}' not found!")
        
        self.texture_map = {}
        for img in image_files:
            for dat in dat_files:
                if img['base_name'] == dat['base_name']:
                    self.texture_map[img['original_name']] = {
                        'image_path': img['image_path'],
                        'dat_path': dat['dat_path'],
                        'bundle': dat['bundle'],
                        'base_name': img['base_name']
                    }
                    break
        
        with open(self.index_file, 'w') as f:
            json.dump(self.texture_map, f, indent=2)
        
        print(f"\nIndex built! Found {len(self.texture_map)} decal mappings.\n")
        return len(self.texture_map)
    
    def load_index(self):
        """Load existing index"""
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r') as f:
                self.texture_map = json.load(f)
            return True
        return False
    
    def find_dat(self, image_name):
        """Find the .DAT file for a given image"""
        if image_name in self.texture_map:
            return self.texture_map[image_name]
        
        base = get_base_name(image_name)
        for img, info in self.texture_map.items():
            if info['base_name'] == base:
                return info
        return None
    
    def search(self, query):
        """Search for textures by partial name"""
        q = query.lower()
        return [(img, info) for img, info in self.texture_map.items()
                if q in img.lower() or q in info['base_name'].lower()]
    
    def get_bundles(self):
        """Get sorted list of unique bundles"""
        return sorted(set(info['bundle'] for info in self.texture_map.values()))
    
    def select_bundle(self, bundle_input, bundles):
        """Select a bundle from input"""
        try:
            idx = int(bundle_input) - 1
            if 0 <= idx < len(bundles):
                return bundles[idx]
        except ValueError:
            if bundle_input in bundles:
                return bundle_input
            
            matches = [b for b in bundles if bundle_input.lower() in b.lower()]
            if len(matches) == 1:
                return matches[0]
            elif len(matches) > 1:
                print(f"\nMultiple bundles match '{bundle_input}':")
                for m in matches:
                    print(f"  - {m}")
                print("\nPlease be more specific.\n")
        return None