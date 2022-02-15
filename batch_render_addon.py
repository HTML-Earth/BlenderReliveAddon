bl_info = {
    # required
    'name': 'Batch Renderer for RELIVE',
    'blender': (2, 93, 0),
    'category': 'Render',
    # optional
    'version': (0, 1, 0),
    'author': 'HTML_Earth',
    'description': 'A tool to render HD sprites for RELIVE',
}

import bpy, os, json, fnmatch
from pathlib import Path
from shutil import copyfile
from collections import namedtuple

# == CUSTOM DATATYPES

# Animation from new asset tool
AnimMeta = namedtuple('AnimMeta', 'name frame_count size_w size_h offset_x offset_y')

# Settings to render a single frame
AnimFrame = namedtuple('AnimFrame', 'name index size_w size_h offset_x offset_y, model, file_path')

# Settings used for reference images and camera (NOTE: same container, but different values)
SizeAndOffsets = namedtuple('SizeAndOffsets', 'size offset_x offset_y')

# == CONSTANTS

# strings
msg_ready = 'READY'
msg_preparing_render = 'PREPARING TO RENDER...'
msg_rendering = 'RENDERING... {}/{}'
msg_copying_duplicates = 'COPYING DUPLICATE FRAMES...'
msg_done = 'DONE'
msg_cancelling = 'CANCELLING...'
msg_cancelled = 'CANCELLED'
msg_check_settings = 'CHECK SETTINGS'
error_no_csv = 'CSV FILE NOT FOUND'

default_resolution_x = 137
default_resolution_y = 180
default_camera_scale = 3.15
default_camera_y_pos = 0.3777

pixel_size = 0.017

# model types
all_model_types = ['default'] #TODO: add 'gibs' as well

# mudokon view layers
mud_all_models = ['abe_game', 'abe_game_orange', 'abe_fmv', 'mud_green_game', 'mud_green_game_orange', 'mud_green_fmv', 'mud_blind_game', 'mud_blind_fmv']
mud_game = ['abe_game', 'mud_green_game', 'mud_blind_game']
mud_game_orange = ['abe_game_orange', 'mud_green_game_orange', 'mud_blind_game']
mud_fmv = ['abe_fmv', 'mud_green_fmv', 'mud_blind_fmv']
mud_abe_game = ['abe_game']
mud_abe_game_orange = ['abe_game_orange']
mud_abe_fmv = ['abe_fmv']

# slig view layers
slig_all_models = ['slig_visor', 'slig_visor_tubes', 'slig_lenses', 'slig_lenses_tubes']

# gluk view layers
gluk_all_models = ['rf_exec_blue', 'rf_exec_brown', 'rf_exec_green', 'rf_exec_greyblue', 'rf_exec_purple', 'rf_exec_red', 'jr_exec', 'jr_exec_gib', 'aslik', 'aslik_gib', 'dripik', 'dripik_gib', 'dripik_menu']
gluk_rf_exec_fmv_green = ['rf_exec_green']
gluk_rf_exec_fmv_all = ['rf_exec_blue', 'rf_exec_brown', 'rf_exec_green', 'rf_exec_greyblue', 'rf_exec_purple', 'rf_exec_red']
gluk_jr_exec_game = ['jr_exec', 'jr_exec_gib']
gluk_aslik_fmv = ['aslik', 'aslik_gib']
gluk_dripik_fmv = ['dripik', 'dripik_gib']
gluk_menu_dripik = ['dripik_menu']

# == GLOBAL VARIABLES

class ReliveBatchProperties(bpy.types.PropertyGroup):

    character_type : bpy.props.EnumProperty(
        name= "Character",
        items= [('mud', "Mudokon", ""),
                ('slig', "Slig", ""),
                ('gluk', "Glukkon", "")
        ]
    )

    # FILE PATHS
    render_path : bpy.props.StringProperty(name='Render Path', default='renders', description="Renders will be saved to this path (relative to .blend file)")
    ref_sprite_path : bpy.props.StringProperty(name='Reference Sprites Path', default='sprites', description="Sprites will be loaded from this path (relative to .blend file)")
    ref_sprite_filter : bpy.props.StringProperty(name='Reference Sprite filter', default='Mudokon*', description="Only animations that match the filter will be imported")

    enabled_view_layers : bpy.props.BoolVectorProperty(
        name = "ViewLayers",
        description = "Which models (ViewLayers) to include passes of when rendering",
        size = 32,
    )

    # CSV
    use_custom_csv : bpy.props.BoolProperty(name='Use custom CSV', default=False, description="Instead of using the default CSV file for the selected character, use a custom path")
    custom_csv_path : bpy.props.StringProperty(name='CSV File', default='debug.csv', description="Path to CSV file containing animation info")

    # SCENE REFS
    camera_name : bpy.props.StringProperty(name='Camera', default='Camera', description="The name of the main camera used to render")
    rig_name : bpy.props.StringProperty(name='Rig', default='rig', description="The name of the main character rig")

    # PRIVATE
    batch_render_status : bpy.props.StringProperty(name='Current status of batch renderer', default=msg_ready)
    is_batch_rendering : bpy.props.BoolProperty(name='Batch rendering is in progress', default=False)
    render_cancelled : bpy.props.BoolProperty(name='Batch render is being cancelled', default=False)
    current_model : bpy.props.StringProperty(name='Current model', default='')
    current_anim : bpy.props.StringProperty(name='Current animation', default='')
    current_frame : bpy.props.StringProperty(name='Current frame', default='')

# == UTILS

def check_model_type(model_type):
    if model_type in all_model_types:
        return True
    return False

def get_anims(sprite_folder, filter):
    anim_folders = [f for f in Path(sprite_folder).iterdir() if f.is_dir()]
    anims = []
    for folder in anim_folders:
        if not fnmatch.fnmatch(folder.name, filter):
            continue

        json_file = folder / 'meta.json'
        if not Path.exists(json_file):
            continue

        with open(json_file) as f:
            data = json.load(f)

            frame_count = data['frame_count']
            size_w = data['size']['w']
            size_h = data['size']['h']
            offset_x = data['offset']['x']
            offset_y = data['offset']['y']

            if frame_count < 1:
                continue

            anims.append(AnimMeta(folder.name, frame_count, size_w, size_h, offset_x, offset_y))

    return anims

def get_models(view_layers, enabled_view_layers):
    models = []
    for i, model in enumerate(view_layers):
        if enabled_view_layers[i] == True:
            models.append(model.name)
    return models

def get_action(action_name):
    # Check all available actions
    for action in bpy.data.actions:
        # Check if action has correct name
        if action.name == action_name:
            return action
        
    print('Action: {} not available'.format(action_name))
    return None

def apply_action(action):
    bpy.context.scene.objects[bpy.context.scene.reliveBatch.rig_name].animation_data.action = bpy.data.actions[action]

def calculate_reference_params(size_w, size_h, offset_x, offset_y):
    # set size depending on aspect ratio
    if size_w > size_h:
        size = size_w * pixel_size
    else:
        size = size_h * pixel_size

    # offsets (x is flipped)
    x = 1 - (offset_x / size_w) - 1
    y =     (offset_y / size_h) - 1

    return SizeAndOffsets(size, x, y)

def calculate_cam_params(size_w, size_h, offset_x, offset_y):
    # set ortho scale depending on aspect ratio
    if size_w > size_h:
        scale = size_w * pixel_size
    else:
        scale = size_h * pixel_size
    
    # offsets
    x = 1 - (offset_x / size_w) - 0.5
    y =     (offset_y / size_h) - 0.5

    return SizeAndOffsets(scale, x, y)

# == OPERATORS

class ReliveImportReferencesOperator(bpy.types.Operator):
    
    bl_idname = 'opr.import_reference_sprites_operator'
    bl_label = 'Reference Sprite Importer'

    def execute(self, context):
        props = context.scene.reliveBatch

        print("Importing reference sprites...")

        anims = get_anims(props.ref_sprite_path, props.ref_sprite_filter)

        # Create ref collections
        referencesCollection = bpy.data.collections.new("References (" + props.ref_sprite_filter + ")")
        bpy.context.scene.collection.children.link(referencesCollection)
        referencesCollection.color_tag = 'COLOR_01'
        referencesCollection.hide_select = True

        # Add all reference image sequences
        for anim in anims:
            # load image and set to sequence
            img = bpy.data.images.load("//" + props.ref_sprite_path + "/" + anim.name + "/0.png")
            img.name = anim.name
            img.source = 'SEQUENCE'

            # create new empty
            empty = bpy.data.objects.new(anim.name, None)

            # set empty to use image sequence
            empty.empty_display_type = 'IMAGE'
            empty.data = img
            
            # set sequence frames
            #   for some reason the frame count starts at 0
            #   and the first frame starts at 1... Blender pls
            empty.image_user.frame_duration = anim.frame_count - 1
            empty.image_user.frame_start = 1

            # enable alpha
            empty.use_empty_image_alpha = True

            # set size and offsets
            empty_img_settings = calculate_reference_params(anim.size_w, anim.size_h, anim.offset_x, anim.offset_y)
            empty.empty_display_size = empty_img_settings.size
            empty.empty_image_offset[0] = empty_img_settings.offset_x
            empty.empty_image_offset[1] = empty_img_settings.offset_y

            # rotate toward camera
            empty.rotation_euler[0] = 1.5708
            empty.rotation_euler[2] = -1.5708

            # add to collection
            referencesCollection.objects.link(empty)

        return {"FINISHED"}

class ReliveSetModelsOperator(bpy.types.Operator):
    
    bl_idname = 'opr.set_batch_view_layers'
    bl_label = 'Batch Renderer View Layer Setter-Upper'

    preset: bpy.props.EnumProperty(
        items=[
            ('mud_all_models', 'mud_all_models', ''),
            ('mud_game', 'mud_game', ''),
            ('mud_fmv', 'mud_fmv', ''),
            ('mud_abe_game', 'mud_abe_game', ''),
            ('mud_abe_fmv', 'mud_abe_fmv', ''),

            ('slig_all_models', 'slig_all_models', ''),

            ('gluk_all_models', 'gluk_all_models', ''),
            ('gluk_rf_exec_fmv_green', 'gluk_rf_exec_fmv_green', ''),
            ('gluk_rf_exec_fmv_all', 'gluk_rf_exec_fmv_all', ''),
            ('gluk_jr_exec_game', 'gluk_jr_exec_game', ''),
            ('gluk_aslik_fmv', 'gluk_aslik_fmv', ''),
            ('gluk_dripik_fmv', 'gluk_dripik_fmv', ''),
            ('gluk_menu_dripik', 'gluk_menu_dripik', ''),
        ]
    )

    def execute(self, context):
        layer_bools = context.scene.reliveBatch.enabled_view_layers
        layers = context.scene.view_layers

        if self.preset == 'mud_all_models':
            preset = mud_all_models
        elif self.preset == 'mud_game':
            preset = mud_game
        elif self.preset == 'mud_fmv':
            preset = mud_fmv
        elif self.preset == 'mud_abe_game':
            preset = mud_abe_game
        elif self.preset == 'mud_abe_fmv':
            preset = mud_abe_fmv
        elif self.preset == 'slig_all_models':
            preset = slig_all_models
        elif self.preset == 'gluk_all_models':
            preset = gluk_all_models
        elif self.preset == 'gluk_rf_exec_fmv_green':
            preset = gluk_rf_exec_fmv_green
        elif self.preset == 'gluk_rf_exec_fmv_all':
            preset = gluk_rf_exec_fmv_all
        elif self.preset == 'gluk_jr_exec_game':
            preset = gluk_jr_exec_game
        elif self.preset == 'gluk_aslik_fmv':
            preset = gluk_aslik_fmv
        elif self.preset == 'gluk_dripik_fmv':
            preset = gluk_dripik_fmv
        elif self.preset == 'gluk_menu_dripik':
            preset = gluk_menu_dripik
        else:
            preset = []

        for i, checkbox in enumerate(layer_bools):
            if i < len(layers):
                layer_bools[i] = layers[i].name in preset
            else:
                layer_bools[i] = False

        return {"FINISHED"}

class ReliveBatchCancelOperator(bpy.types.Operator):
    
    bl_idname = 'opr.batch_cancel_operator'
    bl_label = 'Batch Renderer Canceller'

    def execute(self, context):
        print("Cancelling...")
        context.scene.reliveBatch.batch_render_status = msg_cancelling
        context.scene.reliveBatch.render_cancelled = True
        return {"FINISHED"}

class ReliveBatchRenderOperator(bpy.types.Operator):
    
    bl_idname = 'opr.batch_renderer_operator'
    bl_label = 'Batch Renderer'
    
    full_frame_count = 0

    frames_to_render = []

    missing_actions = []

    _timer = None
    _timer_interval = 0.1
    
    rendering_frame = False
    
    def pre(self, *args, **kwargs):
        self.rendering_frame = True
        bpy.context.scene.reliveBatch.batch_render_status = msg_rendering.format(str(self.full_frame_count - len(self.frames_to_render)), str(self.full_frame_count))

    def post(self, *args, **kwargs):
        self.frames_to_render.pop(0)
        self.rendering_frame = False
    
    def execute(self, context):
        props = context.scene.reliveBatch

        props.is_batch_rendering = True
        props.batch_render_status = msg_preparing_render

        # save old resolution
        self.previous_resolution_x = context.scene.render.resolution_x
        self.previous_resolution_y = context.scene.render.resolution_y
        
        # save old camera settings
        self.previous_camera_scale = bpy.data.cameras[props.camera_name].ortho_scale
        self.previous_camera_y_pos = bpy.data.cameras[props.camera_name].shift_y

        # save old render path
        self.previous_render_path = context.scene.render.filepath

        # save old render display setting
        self.previous_render_display_type = context.preferences.view.render_display_type

        # save old action
        self.previous_action = context.scene.objects[props.rig_name].animation_data.action
        
        try:
            # Get animation list using sprite folder
            animations = get_anims(props.ref_sprite_path, "*")
        except EnvironmentError: # parent of IOError, OSError *and* WindowsError where available
            self.report({"ERROR"}, error_no_csv)
            self.finished(error_no_csv)
            return {"CANCELLED"}

        for anim in animations:
                
                # if action is in missing action list, skip it
                if anim.name in self.missing_actions:
                    continue

                # get action handle from action name
                action = get_action(anim.name)
                # if action is missing, add to list of missing actions
                if action == None:
                    self.missing_actions.append(anim.name)
                    continue
                
                for i in range(anim.frame_count):
                    # make relative path string
                    file_path = Path('{}/{}/{}'.format(props.render_path, anim.name, i))

                    # for each enabled view layer (model)
                    for model in get_models(context.scene.view_layers, props.enabled_view_layers):
                        # Add frame to frames_to_render
                        self.frames_to_render.append(AnimFrame(anim.name, i, anim.size_w, anim.size_h, anim.offset_x, anim.offset_y, model, file_path))
                        self.full_frame_count += 1

        # set render display setting to avoid window popups for each render
        context.preferences.view.render_display_type = 'NONE'

        bpy.app.handlers.render_pre.append(self.pre)
        bpy.app.handlers.render_post.append(self.post)

        # The timer gets created and the modal handler
        # is added to the window manager
        self._timer = context.window_manager.event_timer_add(self._timer_interval, window=context.window)
        context.window_manager.modal_handler_add(self)

        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == 'TIMER': # This event is signaled every _timer_interval seconds
                                  # and will start the render if available

            # If cancelled or no more frames to render, finish.
            if True in (not self.frames_to_render, context.scene.reliveBatch.render_cancelled is True):

                # We remove the handlers and the modal timer to clean everything
                bpy.app.handlers.render_pre.remove(self.pre)
                bpy.app.handlers.render_post.remove(self.post)
                #bpy.app.handlers.render_cancel.remove(self.cancelled)
                context.window_manager.event_timer_remove(self._timer)
                self.finished('CANCELLED' if context.scene.reliveBatch.render_cancelled else 'DONE')
                return {"CANCELLED" if context.scene.reliveBatch.render_cancelled else "FINISHED"}

            elif self.rendering_frame is False: # Nothing is currently rendering.
                                          # Proceed to render.
                sc = context.scene
                props = sc.reliveBatch
                
                # retrieve frame data
                frame = self.frames_to_render[0]

                props.current_model = frame.model
                props.current_anim = frame.name
                props.current_frame = str(frame.index)
                
                # Apply action
                apply_action(frame.name)
                
                # Set current frame
                sc.frame_set(frame.index)
                
                # Set output resolution
                sc.render.resolution_x = frame.size_w
                sc.render.resolution_y = frame.size_h

                camera_settings = calculate_cam_params(frame.size_w, frame.size_h, frame.offset_x, frame.offset_y)
                
                # Setup camera position and scale
                bpy.data.cameras[props.camera_name].ortho_scale = camera_settings.size
                bpy.data.cameras[props.camera_name].shift_x     = camera_settings.offset_x
                bpy.data.cameras[props.camera_name].shift_y     = camera_settings.offset_y

                # Set file path
                sc.render.filepath = '//{}'.format(frame.file_path)

                # Render frame
                bpy.ops.render.render(layer=frame.model, write_still=True)

        return {"PASS_THROUGH"}

    def finished(self, status):
        scene = bpy.context.scene
        props = scene.reliveBatch

        #if not props.render_cancelled:
            # COPY DUPLICATE FRAMES
        #    props.batch_render_status = msg_copying_duplicates
        #    copy_duplicate_frames(self.frames_to_copy)

        # RESET FRAME VARIABLES
        self.frames_to_render = []
        self.full_frame_count = 0

        self.missing_actions = []
        
        # RESET FILEPATH
        scene.render.filepath = self.previous_render_path
        
        # RESET ANIMATION
        scene.objects[props.rig_name].animation_data.action = bpy.data.actions[self.previous_action.name]
        
        # RESET FRAME 
        # causes crash :(
        #scene.frame_set(0)
        
        # RESET RESOLUTION
        scene.render.resolution_x = self.previous_resolution_x
        scene.render.resolution_y = self.previous_resolution_y
        
        # RESET CAMERA
        bpy.data.cameras[props.camera_name].ortho_scale = self.previous_camera_scale
        bpy.data.cameras[props.camera_name].shift_y     = self.previous_camera_y_pos

        # RESET RENDER DISPLAY SETTING
        bpy.context.preferences.view.render_display_type = self.previous_render_display_type
        
        props.current_model = ""
        props.current_anim = ""
        props.current_frame = ""
        
        props.is_batch_rendering = False
        props.render_cancelled = False
        props.batch_render_status = status

        self.rendering_frame = False

# == PANELS

class ReliveBatchRendererPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RELIVE"

class ReliveBatchRendererMainPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer"
    bl_label = "Batch Renderer for RELIVE"

    def draw(self, context):
        props = context.scene.reliveBatch

        col = self.layout.column()

        # Properties
        col.row().prop(props, "character_type", text='')
        
        col.row().label(text='Sprite path:')
        col.row().prop(props, "ref_sprite_path", text='')
        
        col.label(text="Output path:")
        col.row().prop(props, "render_path", text='')
        
        col.row().label(text='')
        col.row().label(text='Tool by HTML_Earth')

class ReliveBatchRendererReferencesPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer_references"
    bl_parent_id = "VIEW3D_PT_batch_renderer"
    bl_label = "Import Reference Sprites"

    def draw(self, context):
        props = context.scene.reliveBatch
        col = self.layout.column()

        col.row().label(text='Filter')
        col.row().prop(props, "ref_sprite_filter", text='')

        col.row().operator('opr.import_reference_sprites_operator', text='IMPORT SPRITES')

class ReliveBatchRendererRenderPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer_render"
    bl_parent_id = "VIEW3D_PT_batch_renderer"
    bl_label = "Render"

    def draw(self, context):
        props = context.scene.reliveBatch

        col = self.layout.column()

        # Render status
        col.label(text=props.batch_render_status)

        # Render/Cancel button
        button_row = col.row()
        if props.is_batch_rendering:
            button_row.operator('opr.batch_cancel_operator', text='CANCEL BATCH')
            if props.render_cancelled:
                button_row.enabled = False
        else:
            button_row.operator('opr.batch_renderer_operator', text='BATCH RENDER')

        # Current render progress
        if props.is_batch_rendering:
            col.label(text="Model: " + props.current_model)
            col.label(text="Anim: " + props.current_anim)
            col.label(text="Frame: " + props.current_frame)
            
class ReliveBatchRendererModelsPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer_models"
    bl_parent_id = "VIEW3D_PT_batch_renderer"
    bl_label = "Render Settings"

    def draw(self, context):
        props = context.scene.reliveBatch
        col = self.layout.column()

        col.label(text="Presets:")

        if props.character_type == 'mud':
            col.row().operator('opr.set_batch_view_layers', text='All models').preset = 'mud_all_models'
            
            row1 = col.row()
            row1.operator('opr.set_batch_view_layers', text='All (Game)').preset = 'mud_game'
            row1.operator('opr.set_batch_view_layers', text='All (FMV)').preset = 'mud_fmv'

            row2 = col.row()
            row2.operator('opr.set_batch_view_layers', text='Abe (Game)').preset = 'mud_abe_game'
            row2.operator('opr.set_batch_view_layers', text='Abe (FMV)').preset = 'mud_abe_fmv'

        elif props.character_type == 'slig':
            col.row().operator('opr.set_batch_view_layers', text='All models').preset = 'slig_all_models'

        elif props.character_type == 'gluk':
            col.row().operator('opr.set_batch_view_layers', text='All models').preset = 'gluk_all_models'

            row1 = col.row()
            row1.operator('opr.set_batch_view_layers', text='Jr. Exec (All)').preset = 'gluk_rf_exec_fmv_all'
            row1.operator('opr.set_batch_view_layers', text='Jr. Exec (Game)').preset = 'gluk_jr_exec_game'

            row2 = col.row()
            row2.operator('opr.set_batch_view_layers', text='Aslik').preset = 'gluk_aslik_fmv'
            row2.operator('opr.set_batch_view_layers', text='Dripik').preset = 'gluk_dripik_fmv'

        col.label(text="View Layers:")
        for i, model in enumerate(context.scene.view_layers):
            col.row().prop(props, "enabled_view_layers", index=i, text=model.name)

class ReliveBatchRendererSettingsPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer_settings"
    bl_parent_id = "VIEW3D_PT_batch_renderer"
    bl_label = "Advanced Settings"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        props = context.scene.reliveBatch
        col = self.layout.column()
        col.label(text="(Used by script to find objects)")
        
        layout = self.layout
        split = layout.split(factor=0.3)
        col_1 = split.column()
        col_2 = split.column()

        # Properties
        col_1.label(text='Camera')
        col_2.row().prop(props, "camera_name", text='')
        col_1.label(text='Rig')
        col_2.row().prop(props, "rig_name", text='')

# == MAIN ROUTINE

CLASSES = [
    ReliveBatchProperties,
    
    ReliveImportReferencesOperator,
    ReliveSetModelsOperator,
    ReliveBatchRenderOperator,
    ReliveBatchCancelOperator,

    ReliveBatchRendererMainPanel,
    ReliveBatchRendererReferencesPanel,
    ReliveBatchRendererRenderPanel,
    ReliveBatchRendererModelsPanel,
    ReliveBatchRendererSettingsPanel,
]

def register():
    for c in CLASSES:
        bpy.utils.register_class(c)

    setattr(bpy.types.Scene, "reliveBatch", bpy.props.PointerProperty(type=ReliveBatchProperties))

def unregister():
    for c in CLASSES:
        bpy.utils.unregister_class(c)

    delattr(bpy.types.Scene, "reliveBatch")

if __name__ == '__main__':
    register()