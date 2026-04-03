import os
import json

VERSION = 5.2
CONFIG_FILE = "decal_tool_config.json"

DEFAULT_CONFIG = {
    "images_dir": "Images",
    "raw_dir": "Raw",
    "texconv_path": "texconv.exe"
}

def load_config():
    """Load configuration from file or create default"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Ensure all required keys exist
                for key in DEFAULT_CONFIG:
                    if key not in config:
                        config[key] = DEFAULT_CONFIG[key]
                return config
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save configuration to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"\nConfiguration saved to {CONFIG_FILE}\n")