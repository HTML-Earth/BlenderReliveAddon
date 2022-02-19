bl_info = {
    # required
    'name': 'Batch Renderer for RELIVE',
    'blender': (2, 93, 0),
    'category': 'Render',
    # optional
    'version': (0, 9, 4),
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

# Settings to render an animation
AnimToRender = namedtuple('AnimToRender', 'meta, model, file_path')

# Settings used for reference images and camera (NOTE: same container, but different values)
SizeAndOffsets = namedtuple('SizeAndOffsets', 'size offset_x offset_y')

# == CONSTANTS

# strings
msg_ready = 'READY'
msg_preparing_render = 'PREPARING TO RENDER...'
msg_rendering = 'RENDERING... {}/{}'
msg_done = 'DONE'
msg_cancelling = 'CANCELLING...'
msg_cancelled = 'CANCELLED'
msg_check_settings = 'CHECK SETTINGS'
error_path = 'PATH ERROR. Do not open the file from within Blender. Start Blender by opening the file directly.'

default_pass_name = "_DEFAULT"
emissive_pass_name = "_emissive"

pixel_size = 0.017

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
        items= [('none', "None", ""),
                ('mud', "Mudokon", ""),
                ('slig', "Slig", ""),
                ('gluk', "Glukkon", "")
        ]
    )

    # FILE PATHS
    render_path : bpy.props.StringProperty(name='Render Path', default='renders', description="Renders will be saved to this path (relative to .blend file)")
    ref_sprite_path : bpy.props.StringProperty(name='Reference Sprites Path', default='sprites', description="Sprites will be loaded from this path (relative to .blend file)")
    
    # Filters
    ref_sprite_filter : bpy.props.StringProperty(name='Reference Sprite filter', default='Mudokon*', description="Only animations that match the filter will be imported")
    animation_filter : bpy.props.StringProperty(name='Exported animation filter', default='*', description="Only animations that match the filter will be rendered")

    # Pass
    pass_to_use : bpy.props.StringProperty(name='Render pass to use', default='', description="This will be appended to the exported filenames (Leave empty for default)\n\n'emissive' - turns off transparency and hides the light collection")

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
    lights_collection : bpy.props.StringProperty(name='Lights', default='Lights', description="The name of the collection containing all lights")

    # PRIVATE
    batch_render_status : bpy.props.StringProperty(name='Current status of batch renderer', default=msg_ready)
    is_batch_rendering : bpy.props.BoolProperty(name='Batch rendering is in progress', default=False)
    render_cancelled : bpy.props.BoolProperty(name='Batch render is being cancelled', default=False)
    current_model : bpy.props.StringProperty(name='Current model', default='')
    current_anim : bpy.props.StringProperty(name='Current animation', default='')

    current_pass : bpy.props.StringProperty(name='Current animation', default=default_pass_name)

# == UTILS

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

def get_enabled_view_layer_count(context):
    enabled_view_layer_count = 0
    for i, model in enumerate(context.scene.view_layers):
        if context.scene.reliveBatch.enabled_view_layers[i]:
            enabled_view_layer_count += 1
    return enabled_view_layer_count

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
    
    # offsets (x is flipped)
    x = 1 - (offset_x / size_w) - 0.5
    y =     (offset_y / size_h) - 0.5

    # camera shift depends on aspect ratio
    if size_w > size_h:
        y = y * size_h / size_w
    else:
        x = x * size_w / size_h

    return SizeAndOffsets(scale, x, y)

# == OPERATORS

class ReliveImportReferencesOperator(bpy.types.Operator):
    
    bl_idname = 'opr.import_reference_sprites_operator'
    bl_label = 'Reference Sprite Importer'

    def execute(self, context):
        props = context.scene.reliveBatch

        print("Importing reference sprites...")

        try:
            anims = get_anims(props.ref_sprite_path, props.ref_sprite_filter)
        except EnvironmentError: # parent of IOError, OSError *and* WindowsError where available
            self.report({"ERROR"}, "Sprite path is invalid")
            return {"CANCELLED"}

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
    
    full_anim_count = 0

    anims_to_render = []

    missing_actions = []

    _timer = None
    _timer_interval = 0.1
    
    rendering_animation = False

    render_multiple_models = False
    
    def pre(self, *args, **kwargs):
        self.rendering_animation = True
        bpy.context.scene.reliveBatch.batch_render_status = msg_rendering.format(str(self.full_anim_count - len(self.anims_to_render)), str(self.full_anim_count))

    def post(self, *args, **kwargs):
        prefix = bpy.context.scene.reliveBatch.current_pass

        export_path = self.anims_to_render.pop(0).file_path
        export_folder = export_path.removesuffix('/' + prefix)
        print(export_folder)

        files = [f for f in Path(export_folder).iterdir() if f.is_file()]

        for file in files:
            print("checking {}".format(file.name))
            if file.name.startswith(prefix) and file.suffix == ".png":
                new_name = file.name.removeprefix(prefix).lstrip('0').removesuffix(".png")
                if new_name == "":
                    new_name = "0"

                if prefix == default_pass_name:
                    new_path = export_folder + "/" + new_name + ".png"
                else:
                    new_path = export_folder + "/" + new_name + prefix + ".png"

                print("renaming to {}".format(new_path))
                file.replace(new_path)
            else:
                print("suffix was {}".format(file.suffix))

        self.rendering_animation = False
    
    def execute(self, context):
        props = context.scene.reliveBatch

        props.is_batch_rendering = True
        props.batch_render_status = msg_preparing_render

        # reset stuff just in case
        self.full_anim_count = 0
        self.anims_to_render = []
        self.missing_actions = []

        # save old duration
        self.previous_frame_end = context.scene.frame_end

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

        # get list of models to render
        models = get_models(context.scene.view_layers, props.enabled_view_layers)

        # cancel if zero models
        if len(models) < 1:
            self.report({"WARNING"}, "No models/view layers selected!")
            self.finished("SELECT A MODEL!")
            return {"CANCELLED"}
        
        try:
            # Get animation list using sprite folder
            animations = get_anims(props.ref_sprite_path, props.animation_filter)
        except EnvironmentError: # parent of IOError, OSError *and* WindowsError where available
            self.report({"ERROR"}, error_path)
            self.finished(error_path)
            return {"CANCELLED"}

        # Set current pass (and make sure it starts with '_')
        props.current_pass = props.pass_to_use if props.pass_to_use != "" else default_pass_name
        if not props.current_pass.startswith('_'):
            props.current_pass = '_' + props.current_pass

        # Set BG to transparent if pass is not emissive
        self.previous_bg_transparent = context.scene.render.film_transparent
        context.scene.render.film_transparent = props.current_pass != emissive_pass_name
        
        if props.current_pass == emissive_pass_name:
            try:
                self.previous_lights_should_be_hidden = {}

                # go through all view layers
                for model in get_models(context.scene.view_layers, props.enabled_view_layers):
                    # check light collection status in this view layer
                    hide_render = context.scene.view_layers[model].layer_collection.children[props.lights_collection].collection.hide_render
                    
                    print("Previous light collection for {} was {}".format(model, hide_render))

                    # add the status to a dict
                    self.previous_lights_should_be_hidden.update({model: hide_render})

                    # hide lights
                    context.scene.view_layers[model].layer_collection.children[props.lights_collection].collection.hide_render = True
            
            except:
                self.report({"ERROR"}, "Could not find lights collection to hide.")
                self.finished("Check Misc./Lights")
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
                
                #for i in range(anim.frame_count):

                # for each enabled view layer (model)
                for model in get_models(context.scene.view_layers, props.enabled_view_layers):
                    # make relative path string (add model name to path if more than one)
                    if len(models) > 1:
                        file_path = '{}/{}/{}/{}'.format(props.render_path, model, anim.name, props.current_pass)
                    else:
                        file_path = '{}/{}/{}'.format(props.render_path, anim.name, props.current_pass)

                    # Add frame to frames_to_render
                    self.anims_to_render.append(AnimToRender(anim, model, file_path))
                    self.full_anim_count += 1

        # set render display setting to avoid window popups for each render
        context.preferences.view.render_display_type = 'NONE'

        bpy.app.handlers.render_pre.append(self.pre)
        bpy.app.handlers.render_complete.append(self.post)

        # The timer gets created and the modal handler
        # is added to the window manager
        self._timer = context.window_manager.event_timer_add(self._timer_interval, window=context.window)
        context.window_manager.modal_handler_add(self)

        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == 'TIMER': # This event is signaled every _timer_interval seconds
                                  # and will start the render if available

            # If cancelled or no more frames to render, finish.
            if True in (not self.anims_to_render, context.scene.reliveBatch.render_cancelled is True):

                # We remove the handlers and the modal timer to clean everything
                bpy.app.handlers.render_pre.remove(self.pre)
                bpy.app.handlers.render_complete.remove(self.post)
                #bpy.app.handlers.render_cancel.remove(self.cancelled)
                context.window_manager.event_timer_remove(self._timer)
                self.finished(msg_cancelled if context.scene.reliveBatch.render_cancelled else msg_done)
                return {"CANCELLED" if context.scene.reliveBatch.render_cancelled else "FINISHED"}

            elif self.rendering_animation is False: # Nothing is currently rendering.
                                          # Proceed to render.
                sc = context.scene
                props = sc.reliveBatch
                
                # retrieve frame data
                render_anim = self.anims_to_render[0]

                props.current_model = render_anim.model
                props.current_anim = render_anim.meta.name
                
                # Apply action
                apply_action(render_anim.meta.name)
                
                # Set current frame
                #sc.frame_set(frame.index)
                # Set animation duration
                sc.frame_end = render_anim.meta.frame_count - 1
                
                # Set output resolution
                sc.render.resolution_x = render_anim.meta.size_w
                sc.render.resolution_y = render_anim.meta.size_h

                camera_settings = calculate_cam_params(render_anim.meta.size_w, render_anim.meta.size_h, render_anim.meta.offset_x, render_anim.meta.offset_y)
                
                # Setup camera position and scale
                bpy.data.cameras[props.camera_name].ortho_scale = camera_settings.size
                bpy.data.cameras[props.camera_name].shift_x     = camera_settings.offset_x
                bpy.data.cameras[props.camera_name].shift_y     = camera_settings.offset_y

                # Set file path
                sc.render.filepath = '//{}'.format(Path(render_anim.file_path))

                # Render frame
                bpy.ops.render.render(animation=True, write_still=False, layer=render_anim.model)

        return {"PASS_THROUGH"}

    def finished(self, status):
        scene = bpy.context.scene
        props = scene.reliveBatch

        # RESET FRAME VARIABLES
        self.anims_to_render = []
        self.full_anim_count = 0

        self.missing_actions = []
        
        # RESET FILEPATH
        scene.render.filepath = self.previous_render_path
        
        # RESET ANIMATION
        scene.objects[props.rig_name].animation_data.action = bpy.data.actions[self.previous_action.name]
        
        # RESET DURATION
        scene.frame_end = self.previous_frame_end

        # RESET RESOLUTION
        scene.render.resolution_x = self.previous_resolution_x
        scene.render.resolution_y = self.previous_resolution_y
        
        # RESET CAMERA
        bpy.data.cameras[props.camera_name].ortho_scale = self.previous_camera_scale
        bpy.data.cameras[props.camera_name].shift_y     = self.previous_camera_y_pos

        # RESET RENDER DISPLAY SETTING
        bpy.context.preferences.view.render_display_type = self.previous_render_display_type

        # RESET BG TRANSPARENCY SETTING
        scene.render.film_transparent = self.previous_bg_transparent

        # RESET LIGHTS COLLECTION RENDERABILITY
        if props.current_pass == emissive_pass_name:
            try:
                # go through all view layers
                for model in get_models(scene.view_layers, props.enabled_view_layers):
                    print("Resetting light collection for {} to {}".format(model, self.previous_lights_should_be_hidden[model]))
                    # reset lights
                    scene.view_layers[model].layer_collection.children[props.lights_collection].collection.hide_render = self.previous_lights_should_be_hidden[model]
            except:
                print("failed to reset light collection renderability")
        
        props.current_model = ""
        props.current_anim = ""
        
        props.is_batch_rendering = False
        props.render_cancelled = False
        props.batch_render_status = status

        self.rendering_animation = False

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

        version = bl_info['version']
        version_string = str.format("{}.{}.{}", version[0],version[1],version[2])

        col.row().label(text='Version ' + version_string + ' by HTML_Earth')

        col.row().separator()

        # Properties
        box = col.box()
        box.row().label(text='Extracted sprites folder:')
        box.row().prop(props, "ref_sprite_path", text='')

class ReliveBatchRendererReferencesPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer_references"
    bl_parent_id = "VIEW3D_PT_batch_renderer"
    bl_label = "Import Sprites"

    def draw(self, context):
        props = context.scene.reliveBatch
        col = self.layout.column()

        col.row().label(text='Filter:')
        col.row().prop(props, "ref_sprite_filter", text='')

        col.row().operator('opr.import_reference_sprites_operator', text='IMPORT SPRITES')

class ReliveBatchRendererRenderPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer_render"
    bl_parent_id = "VIEW3D_PT_batch_renderer"
    bl_label = "Render Sprites"

    def draw(self, context):
        props = context.scene.reliveBatch

        col = self.layout.column()
        
        col.row().label(text='Filter:')
        col.row().prop(props, "animation_filter", text='')

        col.label(text="Output path:")
        col.row().prop(props, "render_path", text='')


        # Infobox
        infobox = col.box()
        infobox.enabled = False
        
        # Render/Cancel button
        button_row = col.row()

        if props.is_batch_rendering:
            # Status
            infobox.label(text=props.batch_render_status)
            infobox.label(text="Model: " + props.current_model)
            infobox.label(text="Anim: " + props.current_anim)

            button_row.operator('opr.batch_cancel_operator', text='CANCEL BATCH')
            if props.render_cancelled:
                button_row.enabled = False

        else:
            vl_count = get_enabled_view_layer_count(context)

            # Status
            status_text = "READY" if vl_count > 0 else "NO VIEWLAYER"
            infobox.label(text=status_text)

            button_row.enabled = vl_count > 0
            button_row.operator('opr.batch_renderer_operator', text='BATCH RENDER')

            
class ReliveBatchRendererModelsPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer_models"
    bl_parent_id = "VIEW3D_PT_batch_renderer"
    bl_label = "Settings"

    def draw(self, context):
        props = context.scene.reliveBatch
        col = self.layout.column()
        
        col.row().label(text='Render pass name:')
        col.row().prop(props, "pass_to_use", text='')
        
        # VIEW LAYERS
        enabled_view_layer_count = get_enabled_view_layer_count(context)
        vl_header = col.row()
        vl_left = vl_header.column()
        vl_right = vl_header.column()
        vl_right.alignment = "RIGHT"

        vl_left.label(text="View Layers:")
        vl_right.label(text="({}/{})".format(enabled_view_layer_count, len(context.scene.view_layers)))
        
        box = col.box()
        for i, model in enumerate(context.scene.view_layers):
            box.row().prop(props, "enabled_view_layers", index=i, text=model.name)

        # PRESETS
        col.label(text="Presets: (not that useful atm)")
        col.row().prop(props, "character_type", text='')

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

        #elif props.character_type == 'gluk':
            #col.row().operator('opr.set_batch_view_layers', text='All models').preset = 'gluk_all_models'

            #row1 = col.row()
            #row1.operator('opr.set_batch_view_layers', text='Jr. Exec (All)').preset = 'gluk_rf_exec_fmv_all'
            #row1.operator('opr.set_batch_view_layers', text='Jr. Exec (Game)').preset = 'gluk_jr_exec_game'

            #row2 = col.row()
            #row2.operator('opr.set_batch_view_layers', text='Aslik').preset = 'gluk_aslik_fmv'
            #row2.operator('opr.set_batch_view_layers', text='Dripik').preset = 'gluk_dripik_fmv'

class ReliveBatchRendererSettingsPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer_settings"
    bl_parent_id = "VIEW3D_PT_batch_renderer"
    bl_label = "Misc."
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
        col_1.label(text='Lights')
        col_2.row().prop(props, "lights_collection", text='')

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