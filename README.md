<div align="center">

# 🎮 G-Blend

**Garry's Mod → Blender Pipeline Tools**

[![Blender](https://img.shields.io/badge/Blender-4.1%2B-orange?logo=blender&logoColor=white)](https://www.blender.org/)
[![GMod](https://img.shields.io/badge/Garry's%20Mod-required-brightgreen)](https://store.steampowered.com/app/4000/Garrys_Mod/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

*Import your GMod scenes, props and ARC9 weapons directly into Blender — with materials, Workshop content and full hierarchy.*

</div>

---

## 📦 What's Inside

This repository contains **two components** that work together:

| Component | What it does |
|-----------|-------------|
| 🟠 **GMod Scene Importer** *(Blender addon)* | Imports GMod scenes (JSON) into Blender with props, models, materials and Workshop cache support |
| 🟢 **GMod Exporter Addon** *(GMod addon)* | Exports GMod scenes to JSON from inside the game. Supports area export, AdvDupe2 clipboard, and ARC9 runtime capture |

> [!NOTE]
> **Live Link** (real-time sync between GMod and Blender) is present in the codebase but is **not included** in this release. It will be released separately in a future update.

---

## ✨ Features

### GMod Scene Importer (Blender)
- 📁 Import full GMod scenes from exported JSON files
- 🔫 Import **ARC9 weapons** with all attachments and proper bone hierarchy
- 🏭 Automatic **Workshop cache** — scans `.gma` files and extracts missing models
- 🎨 Material pulling from GMod's game folder (VMT → Blender nodes)
- 📸 Camera replacement support
- ⚖️ Global scale and rotation controls
- 🧩 Bodygroup support
- 🗂️ Workshop Content + standalone GMA path support

### GMod Exporter Addon (GMod)
- 📤 Export any area of the map to JSON
- 📋 AdvDupe2 clipboard export
- 🔫 ARC9 weapon runtime capture (bones, attachments, materials)
- 🗂️ Built-in file browser for managing exports
- 🧰 Runtime inspectors: Animation, Skeleton, Materials, Attachments, Entity

---

## 🗂️ Repository Structure

```
G-Blend/
├── gmod_scene_importer/     ← Blender addon (install as .zip)
│   ├── __init__.py
│   ├── operators.py         ← Scene & ARC9 import logic
│   ├── operators_cache.py   ← Workshop GMA cache system
│   ├── operators_livelink.py
│   ├── ui.py                ← All panels: Scene, ARC9, Live Link
│   ├── gma_reader.py
│   ├── utils.py
│   └── SourceIO_adv/        ← Bundled SourceIO library (MDL/BSP/VTF)
│
└── gmod_exporter_addon/     ← GMod server-side addon
    ├── addon.json
    └── lua/
        ├── autorun/         ← Auto-loaded scripts
        ├── arc9_runtime/    ← ARC9 capture modules
        └── advdupe2/        ← AdvDupe2 clipboard support
```

---

## 🚀 Installation

### Step 1 — Install the GMod Addon

1. Copy the `gmod_exporter_addon` folder into your GMod addons directory:
   ```
   ...\steamapps\common\GarrysMod\garrysmod\addons\gmod_exporter_addon\
   ```
2. Launch or restart Garry's Mod
3. The addon loads automatically — no extra steps needed

### Step 2 — Install the Blender Addon

1. Open **Blender 4.1+**
2. Go to **Edit → Preferences → Add-ons → Install...**
3. Select the `gmod_scene_importer` folder (zip it first if needed)
4. Enable **"GMod Scene Importer"** in the addon list
5. The panel appears in **3D Viewport → Sidebar (N) → GMod Tools**

---

## 📖 Usage Guide

### Exporting a Scene from GMod

1. Load any GMod map
2. Open the **Spawnmenu → Utilities** or use the console
3. Use the **Exporter** tool to select an area or use AdvDupe2 clipboard
4. Save the exported `.json` file to a known location

### Importing a Scene into Blender

1. Open Blender, go to the **GMod Tools** sidebar tab
2. Under **GMod Scene Importer**:
   - Set **Scene JSON** — path to your exported `.json` file
   - Set **GMod Folder** — path to your `GarrysMod/garrysmod/` folder
   - *(Optional)* Set **Workshop Content** path for addon model support
3. Click **Import Scene**

### Importing an ARC9 Weapon

1. In GMod, use the ARC9 runtime capture tool to export a weapon JSON
2. In Blender, go to the **ARC9 Weapon Importer** tab
3. Set **GMod Folder** and **Weapon JSON** path
4. Choose **Spawn Mode** (Origin / Bone-relative)
5. Click **Import ARC9 Weapon**

### Workshop Cache (Missing Models Fix)

If some models appear missing after import:
1. Set the **Workshop Content** path (Steam's Workshop download folder)
2. Set a **Cache Storage** folder (where extracted GMAs will be stored)
3. Click **Scan & Cache GMAs** — the addon will extract all relevant content automatically
4. Re-run the import

---

## ⚙️ Requirements

| Software | Version |
|----------|---------|
| Blender | 4.1 or newer |
| Garry's Mod | Any recent version |
| Python | Bundled with Blender (no separate install) |

---

## 📋 Releases

| Version | Date | Contents |
|---------|------|---------|
| [v1.0](https://github.com/Sinon1337/G-blend/releases/tag/v1.0) | 11.07.2026 | GMod Scene Importer + ARC9 Weapon Importer + GMod Exporter Addon |

---

## 🙏 Credits

- **SourceIO** — Bundled library for MDL/BSP/VTF parsing ([SourceIO on GitHub](https://github.com/REDxEYE/SourceIO))

---

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.
