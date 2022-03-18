INSTALLING THE ADDON:
(1) Open Blender and go to Edit --> Preferences --> Add-ons --> Install
(2) Find and select relive_render_addon.py
(3) Make sure the checkbox next to "Render: Batch Renderer for RELIVE" is checked
(4) You can close Blender again (preferences should save automatically)

SETTING UP PREREQUISITES:
(1) Download mlgthatsme's HD release (with asset_tool.exe)
(2) Copy your original AO/AE .lvl files into the same folder as the asset tool.
(3) Open the asset tool and select Utilities --> Export All Anims
(4) It should export (most) of the original sprites to "hd/sprites" - this folder is important
(5) I recommend moving any .blend files you want to use into the "hd" folder

IMPORTING REFERENCE SPRITES (OPTIONAL):
(1) Open mudokon_sprites.blend (or similar)
(2) Hover over a 3D view and press N to toggle [SIDE PANE]
(3) There should be a "RELIVE" tab. Select it.
(4) If the .blend file is not in the "hd" folder,
    set "Extracted sprites folder" to the relative path
    of the "sprites" folder mentioned before
(5) In the "Import Sprites" section, you can set a filter.
    This is useful if you don't want to import every single sprite.
    E.g. set it to "Slig*" to only import slig sprites.
(6) With the filter set, press the "IMPORT SPRITES" button, and wait a bit
(7) There should now be a new collection in the outliner with all of the
    imported references, with proper sizes and offsets.

RENDERING SPRITES (Step 1-4 same as above):
(1) Open mudokon_sprites.blend (or similar)
(2) Hover over a 3D view and press N to toggle [SIDE PANE]
(3) There should be a "RELIVE" tab. Select it.
(4) If the .blend file is not in the "hd" folder,
    set "Extracted sprites folder" to the relative path
    of the "sprites" folder mentioned before
(5) In the "Render Sprites" section, set a filter, (* for all animations) and set your output path.
    If you want to render directly into the sprites folder,
    just set it to the same path as "Extracted sprites folder".
(6) In the "Settings" section, you can choose preset models,
    or manually select which view layers to render.
(7) Just press the "BATCH RENDER" button to start rendering.

You can also specify a "Render pass name". This will be appended to the name of each exported file.
If it ends with "emissive", it will also disable transparency and hide the "Lights" collection.