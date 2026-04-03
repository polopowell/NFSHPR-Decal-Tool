"""
NFS:HPR Decal Mod Tool - GUI Application
Wraps the existing command-line modding tool with a modern dark-mode interface.
"""

import os
import sys
import glob
import shutil
import queue
import threading
import io
from dataclasses import dataclass
from typing import Optional
from tkinter import filedialog, messagebox
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor

# ── Critical: fix CWD so all existing modules find their relative paths ──────
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
from PIL import Image, ImageTk

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

# ── Import existing modules (no modifications to them) ────────────────────────
from Modules.config import load_config, save_config
from Modules.decal_locator import DecalLocator
from Modules.dat_module import read_dat_dimensions, write_dat_dimensions
from Modules.image_gen import generate_alpha_mask
from Modules.image_conv import convert_image_to_dat
from Modules.utils import is_alpha_mask, read_image_dimensions
import packer


# ═════════════════════════════════════════════════════════════════════════════
# Configuration
# ═════════════════════════════════════════════════════════════════════════════

EXTRA_DEFAULTS = {"game_dir": "", "output_dir": "Output"}


def load_full_config() -> dict:
    cfg = load_config()
    for k, v in EXTRA_DEFAULTS.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


# ═════════════════════════════════════════════════════════════════════════════
# Data
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class BundleSlot:
    bundle_name: str
    bundle_path: str          # abs path to Raw/BUNDLE_NAME
    main_info: Optional[dict] = None   # texture_map entry for main texture
    alpha_info: Optional[dict] = None  # texture_map entry for alpha mask
    icon_info: Optional[dict] = None   # texture_map entry for icon
    assigned_image: Optional[str] = None  # abs path to new user image


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

SLOT_COLORS = [
    "#2d4a6e", "#2d6e4a", "#6e2d4a", "#6e5a2d",
    "#2d5a6e", "#4a6e2d", "#6e2d5a", "#5a6e2d",
]


def _slot_color(index: int) -> str:
    return SLOT_COLORS[index % len(SLOT_COLORS)]


def _load_thumbnail(path: str, size=(64, 64)) -> Optional[Image.Image]:
    """Load and resize an image, returning a PIL Image or None on failure."""
    try:
        img = Image.open(path)
        img.thumbnail(size, Image.LANCZOS)
        bg = Image.new("RGB", size, (40, 40, 40))
        if img.mode == "RGBA":
            bg.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2), img)
        else:
            if img.mode != "RGB":
                img = img.convert("RGB")
            bg.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
        return bg
    except Exception:
        return None


def _load_preview(path: str, size=(200, 200)) -> Optional[Image.Image]:
    """Load an image for the detail preview panel. Returns PIL Image or None."""
    try:
        img = Image.open(path).convert("RGBA")
        img.thumbnail(size, Image.LANCZOS)
        bg = Image.new("RGB", size, (40, 40, 40))
        bg.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2), img)
        return bg
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════════════════
# SetupDialog
# ═════════════════════════════════════════════════════════════════════════════

class SetupDialog(ctk.CTkToplevel):
    """Modal dialog for configuring tool paths on first run or from Settings."""

    def __init__(self, parent, config: dict, required: bool = False):
        super().__init__(parent)
        self.result: Optional[dict] = None
        self._config = config.copy()

        self.title("NFS:HPR Decal Tool — Setup")
        self.geometry("580x440")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()

        ctk.CTkLabel(self, text="Configure Tool Paths",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 6))
        ctk.CTkLabel(self, text="Fields marked * are required.",
                     text_color="gray60", font=ctk.CTkFont(size=11)).pack(pady=(0, 10))

        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=24, pady=4)

        self._vars: dict[str, tk.StringVar] = {}
        fields = [
            ("raw_dir",       "Raw Directory *",            "Folder with extracted bundles"),
            ("images_dir",    "Images Directory",            "Folder for decal images"),
            ("game_dir",      "Game DECALLIBRARY Path *",   r"e.g. D:\Need For Speed Hot Pursuit Remastered\DECALLIBRARY"),
            ("texconv_path",  "texconv.exe Path",            "DirectXTex converter tool"),
        ]

        for key, label, hint in fields:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=5)

            ctk.CTkLabel(row, text=label, width=220, anchor="w",
                         font=ctk.CTkFont(size=12)).pack(side="left")

            var = tk.StringVar(value=self._config.get(key, ""))
            self._vars[key] = var
            ctk.CTkEntry(row, textvariable=var, width=220,
                         placeholder_text=hint).pack(side="left", padx=6)
            ctk.CTkButton(row, text="Browse", width=70,
                          command=lambda k=key: self._browse(k)).pack(side="left")

        self._err = ctk.CTkLabel(self, text="", text_color="#e05050",
                                  font=ctk.CTkFont(size=11))
        self._err.pack(pady=6)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=8)
        ctk.CTkButton(btn_row, text="Save & Continue", width=150,
                      command=self._save).pack(side="left", padx=8)
        if not required:
            ctk.CTkButton(btn_row, text="Cancel", width=100, fg_color="#444",
                          command=self.destroy).pack(side="left", padx=8)

    def _browse(self, key: str):
        if key == "texconv_path":
            path = filedialog.askopenfilename(
                title="Select texconv.exe",
                filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        else:
            path = filedialog.askdirectory(title=f"Select directory for '{key}'")
        if path:
            self._vars[key].set(path)

    def _save(self):
        raw = self._vars["raw_dir"].get().strip()
        game = self._vars["game_dir"].get().strip()

        if not raw:
            self._err.configure(text="Raw Directory is required.")
            return
        if not os.path.exists(raw):
            self._err.configure(text=f"Raw Directory not found:\n{raw}")
            return
        if not game:
            self._err.configure(text="Game DECALLIBRARY path is required.")
            return
        if not os.path.exists(game):
            self._err.configure(text=f"Game directory not found:\n{game}")
            return

        for k, v in self._vars.items():
            self._config[k] = v.get().strip()
        self.result = self._config
        self.destroy()


# ═════════════════════════════════════════════════════════════════════════════
# ProgressPanel
# ═════════════════════════════════════════════════════════════════════════════

class ProgressPanel(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="#181820", corner_radius=0, height=170)
        self.pack_propagate(False)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(top, text="Progress", font=ctk.CTkFont(weight="bold"),
                     text_color="gray70").pack(side="left")
        self._status = ctk.CTkLabel(top, text="Ready", text_color="gray70")
        self._status.pack(side="right")

        self._bar = ctk.CTkProgressBar(self, height=10)
        self._bar.set(0)
        self._bar.pack(fill="x", padx=12, pady=4)

        self._log = ctk.CTkTextbox(
            self, height=100,
            font=ctk.CTkFont(family="Consolas", size=10),
            state="disabled", fg_color="#111118")
        self._log.pack(fill="x", padx=12, pady=(0, 8))

    def set_status(self, text: str):
        self._status.configure(text=text)

    def set_progress(self, value: float):
        self._bar.set(max(0.0, min(1.0, value)))

    def append_log(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def reset(self):
        self._bar.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._status.configure(text="Ready")


# ═════════════════════════════════════════════════════════════════════════════
# stdout → queue redirect (captures print() output from existing modules)
# ═════════════════════════════════════════════════════════════════════════════

class _QueueWriter(io.TextIOBase):
    def __init__(self, q: queue.Queue):
        self._q = q

    def write(self, s: str) -> int:
        if s and s.strip():
            self._q.put(("log", s.rstrip()))
        return len(s)

    def flush(self):
        pass


# ═════════════════════════════════════════════════════════════════════════════
# ConversionWorker
# ═════════════════════════════════════════════════════════════════════════════

class ConversionWorker:
    def __init__(self, slots: list, config: dict, output_dir: str,
                 progress_queue: queue.Queue):
        self._slots = slots
        self._config = config
        self._output_dir = output_dir
        self._q = progress_queue

    def run(self):
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self._q)
        try:
            self._do_run()
        finally:
            sys.stdout = old_stdout

    def _log(self, text: str):
        self._q.put(("log", text))

    def _progress(self, step: int, total: int, status: str):
        self._q.put(("progress", step / total, status))

    def _do_run(self):
        total = len(self._slots)
        texconv = self._config.get("texconv_path", "texconv.exe")
        game_dir = self._config.get("game_dir", "")
        errors = []

        for i, slot in enumerate(self._slots):
            self._progress(i, total, f"[{i+1}/{total}] {slot.bundle_name}...")
            self._log(f"\n{'=' * 55}")
            self._log(f"[{i+1}/{total}] Converting: {slot.bundle_name}")
            self._log(f"  Image: {slot.assigned_image}")

            try:
                ok = self._convert_slot(slot, texconv)
            except Exception as e:
                self._log(f"  EXCEPTION: {e}")
                ok = False

            if ok:
                self._q.put(("slot_ok", slot.bundle_name))
            else:
                errors.append(slot.bundle_name)
                self._q.put(("slot_error", slot.bundle_name))

        # Copy packed .BIN files to game directory
        if game_dir and os.path.exists(game_dir):
            self._log(f"\nCopying .BIN files → {game_dir}")
            bin_files = glob.glob(os.path.join(self._output_dir, "*.BIN"))
            for f in bin_files:
                dest = os.path.join(game_dir, os.path.basename(f))
                try:
                    shutil.copy2(f, dest)
                    self._log(f"  Copied: {os.path.basename(f)}")
                except Exception as e:
                    self._log(f"  Failed to copy {os.path.basename(f)}: {e}")
        else:
            self._log("\nWarning: game directory not set — skipping copy to game.")

        self._q.put(("done", errors))

    def _convert_slot(self, slot: BundleSlot, texconv: str) -> bool:
        new_image = slot.assigned_image
        main_info = slot.main_info

        if not main_info:
            self._log("  Error: No main texture info found for this bundle.")
            return False

        # ── 1. Read new image dimensions ────────────────────────────────────
        try:
            img = Image.open(new_image)
            img_w, img_h = img.size
            img.close()
        except Exception as e:
            self._log(f"  Error reading image: {e}")
            return False

        # Snap to multiple-of-4 (required for DXT block alignment)
        img_w = (img_w + 3) // 4 * 4
        img_h = (img_h + 3) // 4 * 4

        # ── 2. Update main DAT dimensions if mismatched ──────────────────────
        try:
            dat_w, dat_h = read_dat_dimensions(main_info["dat_path"])
            if (img_w, img_h) != (dat_w, dat_h):
                self._log(f"  Updating dims: {dat_w}x{dat_h} → {img_w}x{img_h}")
                write_dat_dimensions(main_info["dat_path"], img_w, img_h)
            else:
                self._log(f"  Dims match: {img_w}x{img_h}")
        except Exception as e:
            self._log(f"  Warning: Could not update main DAT dims: {e}")

        # ── 3. Regenerate alpha mask ─────────────────────────────────────────
        if slot.alpha_info:
            alpha_info = slot.alpha_info
            alpha_dir = os.path.dirname(alpha_info["image_path"])
            self._log("  Regenerating alpha mask...")
            try:
                out_path, _ = generate_alpha_mask(
                    new_image, alpha_dir, (img_w, img_h), texconv)

                if out_path and os.path.exists(out_path):
                    os.replace(out_path, alpha_info["image_path"])

                    # Update alpha DAT dimensions
                    try:
                        a_w, a_h = read_dat_dimensions(alpha_info["dat_path"])
                        if (a_w, a_h) != (img_w, img_h):
                            write_dat_dimensions(alpha_info["dat_path"], img_w, img_h)
                    except Exception:
                        pass

                    # Convert alpha image → _texture.dat
                    alpha_tex_dat = alpha_info["dat_path"].replace(".dat", "_texture.dat")
                    self._log("  Converting alpha mask to texture data...")
                    convert_image_to_dat(alpha_info["image_path"], alpha_tex_dat, texconv)
                else:
                    self._log("  Warning: Alpha mask generation produced no output.")
            except Exception as e:
                self._log(f"  Warning: Alpha mask error: {e}")

        # ── 4. Convert main texture → _texture.dat ───────────────────────────
        texture_dat = main_info["dat_path"].replace(".dat", "_texture.dat")
        self._log("  Converting main texture...")
        if not convert_image_to_dat(new_image, texture_dat, texconv):
            self._log("  Error: Main texture conversion failed.")
            return False

        # ── 5. Pack bundle into .BIN ─────────────────────────────────────────
        self._log("  Packing bundle...")
        if not packer.pack_bundle(slot.bundle_path, self._output_dir):
            self._log("  Error: Packing failed.")
            return False

        self._log(f"  ✓ Done: {slot.bundle_name}")
        return True


# ═════════════════════════════════════════════════════════════════════════════
# App base (conditionally includes TkinterDnD.DndMixin)
# ═════════════════════════════════════════════════════════════════════════════

if HAS_DND:
    _AppBase = type("_AppBase", (ctk.CTk, TkinterDnD.DnDWrapper), {})
else:
    _AppBase = ctk.CTk


# ═════════════════════════════════════════════════════════════════════════════
# Main App Window
# ═════════════════════════════════════════════════════════════════════════════

class App(_AppBase):
    def __init__(self):
        super().__init__()
        self.title("NFS:HPR Vinyl Modder (Lite)")
        self.geometry("800x600")
        self.minsize(600, 500)

        if HAS_DND:
            self.TkdndVersion = TkinterDnD._require(self)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self._config = load_full_config()
        self._locator = DecalLocator(
            images_dir=self._config.get("images_dir", "Images"),
            raw_dir=self._config.get("raw_dir", "Raw"),
        )
        self._q: queue.Queue = queue.Queue()
        self._worker: Optional[threading.Thread] = None

        self._build_ui()
        self.after(150, self._startup)

    def _build_ui(self):
        # Title bar
        title_bar = ctk.CTkFrame(self, height=52, fg_color="#12121e", corner_radius=0)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        ctk.CTkLabel(title_bar, text="NFS:HPR  VINYL MODDER",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#4fa3e0").pack(side="left", padx=20)
        ctk.CTkButton(title_bar, text="⚙ Settings", width=100,
                      fg_color="#252540", hover_color="#35356a",
                      command=self._open_settings).pack(side="right", padx=14, pady=9)

        # Content area
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=20)

        # -- Progress panel (bottom) --
        self._progress = ProgressPanel(self)
        self._progress.pack(fill="x", side="bottom")

        # -- Convert Button (anchored at bottom of content) --
        self._convert_btn = ctk.CTkButton(
            content, text="▶ Convert & Install", height=40, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1a6e2a", hover_color="#22883a",
            command=self._start_conversion)
        self._convert_btn.pack(side="bottom", pady=(10, 0))

        # -- Image Selection --
        img_frame = ctk.CTkFrame(content, fg_color="#1e1e2e", corner_radius=8)
        img_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(img_frame, text="1. Select Image", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        row1 = ctk.CTkFrame(img_frame, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(0, 10))
        
        self._image_var = tk.StringVar()
        self._image_entry = ctk.CTkEntry(row1, textvariable=self._image_var, placeholder_text="Drag & drop image here or browse...")
        self._image_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        if HAS_DND:
            self._image_entry.drop_target_register(DND_FILES)
            self._image_entry.dnd_bind("<<Drop>>", self._on_drop)
            
        ctk.CTkButton(row1, text="Browse", width=100, command=self._browse_image).pack(side="left")

        # -- Slot Selection --
        slot_frame = ctk.CTkFrame(content, fg_color="#1e1e2e", corner_radius=8)
        slot_frame.pack(fill="both", expand=True, pady=10)
        ctk.CTkLabel(slot_frame, text="2. Select Decal Slot (Bundle)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        row2 = ctk.CTkFrame(slot_frame, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(0, 5))
        
        self._bundle_var = tk.StringVar()
        self._search_entry = ctk.CTkEntry(row2, textvariable=self._bundle_var, placeholder_text="Type to search bundles...")
        self._search_entry.pack(side="left", fill="x", expand=True)
        self._search_entry.bind("<KeyRelease>", self._filter_combo)

        self._preview_lbl = ctk.CTkLabel(row2, text="Preview", width=64, height=64, fg_color="#1a2a3a", corner_radius=6)
        self._preview_lbl.pack(side="right", padx=10)

        # Scrollable Listbox
        list_frame = ctk.CTkFrame(slot_frame, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self._listbox = tk.Listbox(list_frame, bg="#2b2b2b", fg="white", 
                                   selectbackground="#1f6aa5", highlightthickness=0,
                                   font=("Consolas", 11), relief="flat")
        self._listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ctk.CTkScrollbar(list_frame, command=self._listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self._listbox.config(yscrollcommand=scrollbar.set)
        self._listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        row3 = ctk.CTkFrame(slot_frame, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(row3, text="Recent Conversions:").pack(side="left", padx=(0, 5))
        self._hist_var = tk.StringVar()
        self._hist_combo = ctk.CTkComboBox(row3, variable=self._hist_var, values=["None"], command=self._on_hist_select)
        self._hist_combo.pack(side="left", fill="x", expand=True)

    def _populate_history(self):
        history = self._config.get("history", [])
        if history:
            self._hist_combo.configure(values=list(reversed(history)))
            self._hist_combo.set("Select a recent...")
        else:
            self._hist_combo.configure(values=["No history yet"])

    def _on_hist_select(self, b_name):
        if b_name and b_name not in ("None", "No history yet", "Select a recent..."):
            self._bundle_var.set(b_name)
            self._load_bundle_preview(b_name)

    def _filter_combo(self, event=None):
        q = self._bundle_var.get().lower()
        if not hasattr(self, '_bundles') or not self._bundles: return
        
        self._listbox.delete(0, "end")
        for b in self._bundles:
            if q in b.lower():
                self._listbox.insert("end", b)

    def _on_listbox_select(self, event):
        sel = self._listbox.curselection()
        if not sel: return
        b_name = self._listbox.get(sel[0])
        
        # This is the "Selecting it into the menu slot" fix
        self._bundle_var.set(b_name)
        # Update preview
        self._load_bundle_preview(b_name)

    def _load_bundle_preview(self, b_name):
        if not hasattr(self, '_locator'): return
        
        main_img = None
        icon_img = None
        
        for img_name, info in self._locator.texture_map.items():
            if info.get("bundle") == b_name:
                p = info.get("image_path", "")
                if os.path.exists(p) and not is_alpha_mask(p):
                    dims = read_image_dimensions(p)
                    if dims == (128, 128):
                        icon_img = p
                    else:
                        main_img = p
        
        # Prefer the UI icon (128x128) because large textures are often uncolored white silhouettes
        img_path = icon_img if icon_img else main_img
        
        if img_path:
            pil = _load_preview(img_path, size=(64, 64))
            if pil:
                self._preview_ctk = ctk.CTkImage(pil, size=(64, 64))
                self._preview_lbl.configure(image=self._preview_ctk, text="")
                return
        self._preview_lbl.configure(image=None, text="None")

    def _startup(self):
        raw_dir = self._config.get("raw_dir", "Raw")
        game_dir = self._config.get("game_dir", "")

        if not os.path.exists(raw_dir) or not game_dir:
            self._open_settings(required=True)
            raw_dir = self._config.get("raw_dir", "Raw")
            game_dir = self._config.get("game_dir", "")
            if not os.path.exists(raw_dir) or not game_dir:
                self._progress.set_status("Setup incomplete. Click ⚙ Settings to configure.")
                return

        self._locator = DecalLocator(
            images_dir=self._config.get("images_dir", "Images"),
            raw_dir=raw_dir,
        )

        if not self._locator.load_index():
            if messagebox.askyesno(
                    "Build Index",
                    "No decal index found.\n\nBuild it now? "
                    "(This scans your Raw/ directory — may take a moment.)"):
                self._progress.set_status("Building decal index...")
                self.update()
                self._locator.build_index()
            else:
                self._progress.set_status("No index. Use ⚙ Settings or rebuild manually.")
                return

        self._progress.set_status("Ready.")
        bundles = sorted(self._locator.get_bundles())
        self._bundles = bundles
        self._filter_combo() # Initially fill listbox
        if bundles:
            self._bundle_combo_set_dummy = bundles[0] # not used anymore but good for state
            self._load_bundle_preview(bundles[0])
        self._populate_history()

    def _on_drop(self, event):
        raw = event.data.strip()
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        path = raw.split("} {")[0] if "} {" in raw else raw.split()[0]
        if os.path.isfile(path):
            self._image_var.set(path)

    def _browse_image(self):
        path = filedialog.askopenfilename(
            title="Select decal image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.dds *.tga"),
                       ("All files", "*.*")])
        if path:
            self._image_var.set(path)

    def _open_settings(self, required: bool = False):
        dlg = SetupDialog(self, self._config, required=required)
        self.wait_window(dlg)
        if dlg.result:
            self._config = dlg.result
            save_config(self._config)

    def _start_conversion(self):
        new_image = self._image_var.get().strip()
        bundle_name = self._bundle_var.get().strip()
        
        if not new_image or not os.path.exists(new_image):
            messagebox.showwarning("Missing Image", "Please select a valid image file.")
            return
            
        if not bundle_name:
            messagebox.showwarning("Missing Slot", "Please select a decal slot.")
            return

        game_dir = self._config.get("game_dir", "")
        if not game_dir or not os.path.exists(game_dir):
            messagebox.showerror("Game Directory Missing",
                                 "Game DECALLIBRARY path is not set or not found.\n"
                                 "Please configure it in ⚙ Settings.")
            return

        output_dir = self._config.get("output_dir", "Output")

        # Dynamically build the slot
        raw_dir = self._config.get("raw_dir", "Raw")
        bundle_path = os.path.join(raw_dir, bundle_name)
        slot = BundleSlot(bundle_name=bundle_name, bundle_path=bundle_path, assigned_image=new_image)

        for img_name, info in self._locator.texture_map.items():
            if info.get("bundle") == bundle_name:
                img_path = info.get("image_path", "")
                if os.path.exists(img_path):
                    dims = read_image_dimensions(img_path)
                    if dims == (128, 128):
                        slot.icon_info = info
                    elif is_alpha_mask(img_path):
                        slot.alpha_info = info
                    else:
                        slot.main_info = info

        if not slot.main_info:
            messagebox.showerror("Error", f"No main texture info found for bundle {bundle_name}.")
            return

        self._convert_btn.configure(state="disabled")
        self._progress.reset()
        self._progress.set_status("Converting...")

        hist = self._config.get("history", [])
        if bundle_name in hist: hist.remove(bundle_name)
        hist.append(bundle_name)
        self._config["history"] = hist[-30:] # keep 30
        save_config(self._config)
        self._populate_history()

        worker = ConversionWorker(
            slots=[slot],
            config=self._config,
            output_dir=output_dir,
            progress_queue=self._q,
        )
        self._worker = threading.Thread(target=worker.run, daemon=True)
        self._worker.start()
        self.after(50, self._poll_queue)

    def _poll_queue(self):
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._progress.append_log(msg[1])
                elif kind == "progress":
                    _, val, status = msg
                    self._progress.set_progress(val)
                    self._progress.set_status(status)
                elif kind == "done":
                    self._on_done(msg[1])
                    return
        except queue.Empty:
            pass

        if self._worker and self._worker.is_alive():
            self.after(50, self._poll_queue)

    def _on_done(self, errors: list):
        self._progress.set_progress(1.0)
        self._convert_btn.configure(state="normal")

        if errors:
            self._progress.set_status(f"Finished with {len(errors)} error(s).")
            messagebox.showerror(
                "Conversion Finished with Errors",
                f"{len(errors)} slot(s) failed:\n\n" + "\n".join(errors))
        else:
            self._progress.set_status("All done! Decals installed to game directory.")
            messagebox.showinfo(
                "Success!",
                "All decals converted and installed.\n\n"
                "Launch NFS Hot Pursuit Remastered to see your custom decals!")


# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
