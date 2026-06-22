# Advanced Layout Manager Browser

Advanced Layout Manager Browser is a QGIS plugin that provides a modern dockable browser for managing Print Layouts.

The plugin allows users to organise layouts into custom groups and subgroups, quickly search layouts, manage favourites, and export groups of layouts directly to PDF.

Unlike traditional layout management workflows, Advanced Layout Manager Browser adds an additional organisational layer while keeping layouts as standard QGIS layouts.

---

## Features

### Layout Organisation

* Create custom layout groups
* Create nested subgroups
* Organise layouts using drag-and-drop
* Move layouts between groups
* Colour-code groups for improved visibility
* Display layout counters for groups and subgroups

### Layout Management

* Create new layouts directly from the browser
* Open layouts directly from the browser
* Duplicate existing layouts
* Rename layouts
* Delete layouts
* Mark layouts as favourites

### Search and Navigation

* Instant search and filtering
* Dedicated favourites section
* Dockable browser integrated into the QGIS interface

### Export

* Export all layouts within a group to PDF
* Batch export multiple layouts in a single operation

### Project Integration

* Layout organisation is stored inside the QGIS project
* Groups can be shared with other users working on the same project
* Layouts remain standard QGIS layouts and can be used without the plugin

---

## How It Works

The plugin does not modify QGIS layouts.

Instead, it stores a lightweight mapping between layout names and group paths inside the QGIS project file.

Example:

Project
├── Reports
│   ├── Site Plan
│   ├── Trench Plan
│   └── Context Plan
│
└── Figures
├── Figure 01
├── Figure 02
└── Figure 03

All layouts remain standard QGIS Print Layouts and continue to work normally within QGIS.

---

## Installation

### QGIS Plugin Repository

1. Open QGIS.
2. Go to **Plugins → Manage and Install Plugins**.
3. Search for **Advanced Layout Manager Browser**.
4. Click **Install Plugin**.

### Manual Installation

1. Download the latest release ZIP file.
2. Extract it into your QGIS plugins directory.
3. Restart QGIS.
4. Enable the plugin from the Plugin Manager.

---

## Usage

### Creating Groups

1. Open the plugin panel.
2. Click **New Group**.
3. Enter a group name.

### Creating Subgroups

1. Select an existing group.
2. Click **New Subgroup**.
3. Enter a subgroup name.

### Organising Layouts

Layouts can be:

* Dragged into groups
* Moved using the context menu
* Created directly inside a selected group

### Favourites

Frequently used layouts can be added to the **Favourites** section for quick access.

### Exporting

1. Select a group.
2. Click **Export Group**.
3. Choose an output folder.
4. The plugin exports all layouts within the selected group as PDF files.

---

## Compatibility

Tested with:

* QGIS 3.28 LTR
* QGIS 3.40+
* QGIS 3.44
* QGIS 4.x

Compatible with:

* Qt5
* Qt6

No Processing framework dependency.

---

## Why This Plugin?

Large projects often contain dozens or even hundreds of layouts.

QGIS provides excellent layout creation tools but limited organisational capabilities when many layouts are present.

Advanced Layout Manager Browser was created to provide:

* Better organisation
* Faster navigation
* Improved productivity
* Shared layout structures within projects

while preserving complete compatibility with native QGIS layouts.

---

## License

GPL-2.0-or-later

---

## Author

Valerio Pinna

Pre-Construct Archaeology (PCA)

United Kingdom

---

## Support

If you encounter a bug or would like to suggest a feature, please open an issue on the GitHub repository.
