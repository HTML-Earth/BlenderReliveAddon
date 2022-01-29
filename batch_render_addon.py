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

import bpy, os, csv, itertools
from pathlib import Path
from shutil import copyfile
from collections import namedtuple

# == CUSTOM DATATYPES

# Animation info collected from each row in csv file
AnimInfo = namedtuple('AnimInfo', 'id frame_string width height model_type')
    # id - name of BAN/BND and id (used for folder/file names)
    # frame_string - string describing which frames to use
    # width - img width
    # height - img height
    # model_type - model/collection to use

# Frame info parsed from frame string
FrameInfo = namedtuple('FrameInfo', 'index action_name action_frame')
    # index - the index of the animation which this frame represents
    # action_name - the name of the blender action to use
    # action_frame - which frame of the blender action to use

# Data needed to render a single frame (multiple of these are generated for each AnimInfo)
RenderFrame = namedtuple('RenderFrame', 'anim_id frame_index width height action action_frame model file_path')
    # anim_id - name of BAN/BND and id (used for folder/file names)
    # frame_index - the index of the previous anim_id which this frame represents
    # width - img width
    # height - img height
    # action - which blender action to use
    # action_frame - which frame of the blender action to use
    # model - which model to use (this is the name of a view layer in blender)
    # file_path - the rendered image's output file path

# == CONSTANTS

previous_render_display_type = bpy.context.preferences.view.render_display_type

default_resolution_x = 137
default_resolution_y = 180
default_camera_scale = 3.15
default_camera_y_pos = 0.3777

# model types
all_model_types = ['default'] #TODO: add 'gibs' as well

# view layer presets
all_models = ['abe_game', 'abe_game_orange', 'abe_fmv', 'mud_green_game', 'mud_green_game_orange', 'mud_green_fmv', 'mud_blind_game', 'mud_blind_fmv']

only_game = ['abe_game', 'mud_green_game', 'mud_blind_game']
only_game_orange = ['abe_game_orange', 'mud_green_game_orange', 'mud_blind_game']
only_fmv = ['abe_fmv', 'mud_green_fmv', 'mud_blind_fmv']

only_abe_game = ['abe_game']
only_abe_game_orange = ['abe_game_orange']
only_abe_fmv = ['abe_fmv']

# == GLOBAL VARIABLES

class ReliveBatchProperties(bpy.types.PropertyGroup):

    character_type : bpy.props.EnumProperty(
        name= "Character",
        items= [('mud', "Mudokon", ""),
                ('slig', "Slig", ""),
                ('gluk', "Glukkon", "")
        ]
    )

    render_path : bpy.props.StringProperty(name='Render Path', default='renders', description="Renders will be saved to this path")

    #('add_version', bpy.props.BoolProperty(name='Bool', default=False)),
    #('version', bpy.props.IntProperty(name='Int', default=1)),

    enabled_view_layers : bpy.props.BoolVectorProperty(
        name = "ViewLayers",
        description = "Which models (ViewLayers) to include passes of when rendering",
        size = 32,
    )

    # CSV
    use_custom_csv : bpy.props.BoolProperty(name='Use custom CSV', default=False, description="Instead of using the default CSV file for the selected character, use a custom path")
    custom_csv_path : bpy.props.StringProperty(name='CSV File', default='abe_animlist_debug.csv', description="Path to CSV file containing animation info")

    # REFS
    camera_name : bpy.props.StringProperty(name='Camera', default='Camera', description="The name of the main camera used to render")
    rig_name : bpy.props.StringProperty(name='Rig', default='rig', description="The name of the main character rig")

    # PRIVATE
    batch_render_status : bpy.props.StringProperty(name='Current status of batch renderer', default='READY')
    is_batch_rendering : bpy.props.BoolProperty(name='Batch rendering is in progress', default=False)
    render_cancelled : bpy.props.BoolProperty(name='Batch render is being cancelled', default=False)
    current_model : bpy.props.StringProperty(name='Current model', default='')
    current_anim : bpy.props.StringProperty(name='Current animation', default='')
    current_frame : bpy.props.StringProperty(name='Current frame', default='')

# == UTILS

#def batch_render(params):
#    (view_layer, version, add_version) = params #TODO: update parameters
#    print("RENDER'D!")

def get_default_csv(character_type):
    if character_type == 'mud':
        return 'mud_anims.csv'
    elif character_type == 'slig':
        return 'slig_anims.csv'
    elif character_type == 'gluk':
        return 'gluk_anims.csv'
    else:
        return 'anims.csv'

def check_model_type(model_type):
    if model_type in all_model_types:
        return True
    return False

# Parses string and returns list of FrameInfos
def get_frame_list(frame_string):
    frame_list = []
    frame_index = 0
    
    for anim_access in frame_string.split(";"):
        action_name = anim_access.split(":")[0][1:]
        frames = anim_access.split(":")[1]
        
        if "," in frames:
            for frame in frames.split(","):
                frame_info = FrameInfo(frame_index, action_name, int(frame))
                frame_list.append(frame_info)
                frame_index += 1
        else:
            for i in range(int(frames)):
                frame_info = FrameInfo(frame_index, action_name, i)
                frame_list.append(frame_info)
                frame_index += 1
                
    return frame_list

def get_models(view_layers, enabled_view_layers):
    models = []
    for i, model in enumerate(view_layers):
        if enabled_view_layers[i] == True:
            models.append(model.name)
    return models

def get_action(action_name):
    # Check all available actions
    for action in  bpy.data.actions:
        # Check if action has correct name
        if action.name == action_name:
            return action
        
    print('Action: {} not available'.format(action_name))
    return None

def copy_duplicate_frames(frames_to_copy):
    print('COPYING DUPLICATE FRAMES...')
    for dupe in frames_to_copy:
        src = os.path.realpath(bpy.path.abspath('{}.png'.format(dupe[0])))
        dst = os.path.realpath(bpy.path.abspath('{}.png'.format(dupe[1])))

        #print('source: {}\ndestination: {}'.format(src, dst))
        if not os.path.isdir(os.path.dirname(dst)):
            os.mkdir(os.path.dirname(dst))

        print('COPYING {} TO {}'.format(src, dst))
        copyfile(src, dst)

def apply_action(action):
    bpy.context.scene.objects[bpy.context.scene.reliveBatch.rig_name].animation_data.action = action

def calculate_cam_scale(width, height):
    return 0.0175 * height
    
def calculate_cam_y(width, height):
    return 0.5 - (22 / height)

# == OPERATORS

class ReliveSetModelsOperator(bpy.types.Operator):
    
    bl_idname = 'opr.set_batch_view_layers'
    bl_label = 'Batch Renderer View Layer Setter-Upper'

    preset: bpy.props.EnumProperty(
        items=[
            ('all_models', 'all_models', ''),
            ('only_game', 'only_game', ''),
            ('only_fmv', 'only_fmv', ''),
            ('only_abe_game', 'only_abe_game', ''),
            ('only_abe_fmv', 'only_abe_fmv', '')
        ]
    )

    def execute(self, context):
        layer_bools = context.scene.reliveBatch.enabled_view_layers
        layers = context.scene.view_layers

        if self.preset == 'all_models':
            preset = all_models
        elif self.preset == 'only_game':
            preset = only_game
        elif self.preset == 'only_fmv':
            preset = only_fmv
        elif self.preset == 'only_abe_game':
            preset = only_abe_game
        elif self.preset == 'only_abe_fmv':
            preset = only_abe_fmv
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
        context.scene.reliveBatch.batch_render_status = 'CANCELLING...'
        context.scene.reliveBatch.render_cancelled = True
        return {"FINISHED"}

class ReliveBatchRenderOperator(bpy.types.Operator):
    
    bl_idname = 'opr.batch_renderer_operator'
    bl_label = 'Batch Renderer'
    
    full_frame_count = 0

    frames_to_render = []
    frames_to_copy = []

    _timer = None
    _timer_interval = 0.1
    
    rendering_frame = False
    
    #def cancelled(self, *args, **kwargs):
    #    self.render_cancelled = True
    #    print("CANCELLED")
    #    self.finished()

    def pre(self, *args, **kwargs):
        self.rendering_frame = True
        bpy.context.scene.reliveBatch.batch_render_status = 'RENDERING... ' + str(self.full_frame_count - len(self.frames_to_render)) + "/" + str(self.full_frame_count)

    def post(self, *args, **kwargs):
        self.frames_to_render.pop(0)
        self.rendering_frame = False
        
        if len(self.frames_to_render) < 1:
            print("DONE")
            self.finished()
    
    def execute(self, context):
        #params = (
        #    context.scene.render_path,
        #    context.scene.csv_path,
        #    context.scene.view_layer
        #)

        props = context.scene.reliveBatch

        context.preferences.view.render_display_type = 'NONE'

        props.is_batch_rendering = True
        props.batch_render_status = 'PREPARING TO RENDER...'

        # Get CSV path
        if props.use_custom_csv:
            csv_path = props.custom_csv_path
        else:
            csv_path = get_default_csv(props.character_type)
        
        # Gather all frames from csv into collection
        with open(csv_path) as csvfile:
            rdr = csv.reader(csvfile)
            for i, row in enumerate( rdr ):
                if i == 0:
                    continue
                
                # create AnimInfo from current row
                anim = AnimInfo(row[0], row[1], int(row[2]), int(row[3]), row[4])
                
                # check if model type is available
                if not check_model_type(anim.model_type):
                    print('Model type: {} not available'.format(anim.model_type))
                    continue
                
                # parse frame string to get list of frames
                frame_list = get_frame_list(anim.frame_string)

                # for each enabled view layer (model)
                for model in get_models(context.scene.view_layers, props.enabled_view_layers):
                    # for each frame in frame list
                    for frame_info in frame_list:
                        # get action handle from action name
                        action = get_action(frame_info.action_name)
                        # if action is not null
                        if not action == None:
                            # assume that the frame is unique
                            unique = True

                            # make relative path string
                            file_path = Path('{}/{}/{}/{}_{}'.format(props.render_path, model, anim.id.split('_')[0], anim.id, frame_info.index))

                            for prev_frame in self.frames_to_render:
                                # if frame already in self.frames_to_render
                                if prev_frame.action == action and prev_frame.action_frame == frame_info.action_frame and prev_frame.model == model and prev_frame.width == anim.width and prev_frame.height == anim.height:
                                    # frame is no longer considered unique
                                    unique = False
                                    # add frame to frames_to_copy instead
                                    self.frames_to_copy.append((prev_frame.file_path, file_path))
                                    print('{} will be copied to {}'.format(prev_frame.file_path, file_path))
                                    break

                            if unique:
                                # Add frame to frames_to_render
                                self.frames_to_render.append(RenderFrame(anim.id, frame_info.index, anim.width, anim.height, action, frame_info.action_frame, model, file_path))
                                self.full_frame_count += 1

        # save old render path
        self.previous_render_path = context.scene.render.filepath

        # save old action
        self.previous_action = context.scene.objects[props.rig_name].animation_data.action

        bpy.app.handlers.render_pre.append(self.pre)
        bpy.app.handlers.render_post.append(self.post)
        #bpy.app.handlers.render_cancel.append(self.cancelled)

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
                self.finished()
                return {"FINISHED"}

            elif self.rendering_frame is False: # Nothing is currently rendering.
                                          # Proceed to render.
                sc = context.scene
                
                # retrieve frame data
                frame = self.frames_to_render[0]

                sc.reliveBatch.current_model = frame.model
                sc.reliveBatch.current_anim = frame.action.name
                sc.reliveBatch.current_frame = str(frame.action_frame)
                
                # Apply action
                apply_action(frame.action)
                
                # Set current frame
                sc.frame_set(frame.action_frame)
                
                # Set output resolution
                sc.render.resolution_x = frame.width
                sc.render.resolution_y = frame.height
                
                # Setup camera position and scale
                bpy.data.cameras[sc.reliveBatch.camera_name].ortho_scale = calculate_cam_scale(frame.width, frame.height)
                bpy.data.cameras[sc.reliveBatch.camera_name].shift_y     = calculate_cam_y    (frame.width, frame.height)

                # Set file path
                sc.render.filepath = '//{}'.format(frame.file_path)

                # Render frame
                bpy.ops.render.render("INVOKE_DEFAULT", layer=frame.model, write_still=True)

        return {"PASS_THROUGH"}

    def finished(self):
        scene = bpy.context.scene
        props = scene.reliveBatch

        props.batch_render_status = 'COPYING DUPLICATE FRAMES...'
        # COPY DUPLICATE FRAMES
        copy_duplicate_frames(self.frames_to_copy)
        
        # RESET FILEPATH
        scene.render.filepath = self.previous_render_path
        
        # RESET ANIMATION
        scene.objects[props.rig_name].animation_data.action = bpy.data.actions[self.previous_action.name]
        
        # RESET FRAME 
        # causes crash :(
        #bpy.context.scene.frame_set(0)
        
        # RESET RESOLUTION
        scene.render.resolution_x = default_resolution_x
        scene.render.resolution_y = default_resolution_y
        
        # RESET CAMERA
        bpy.data.cameras[props.camera_name].ortho_scale = default_camera_scale
        bpy.data.cameras[props.camera_name].shift_y     = default_camera_y_pos

        bpy.context.preferences.view.render_display_type = previous_render_display_type
        
        props.current_model = ""
        props.current_anim = ""
        props.current_frame = ""
        
        props.is_batch_rendering = False
        props.render_cancelled = False
        props.batch_render_status = 'DONE'

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

        #layout = self.layout
        #split = layout.split(factor=0.25)
        #col_1 = split.column()
        #col_2 = split.column()
        #col_1.label(text='Add mesh')
        #col_2.operator('mesh.primitive_cube_add', text='Cube')
        #col_1.label(text='Word name')
        #col_2.prop(bpy.data.worlds['World'], 'name', text='')

        col = self.layout.column()

        # Properties
        col.row().prop(props, "character_type", text='')
        col.label(text="Output path:")
        col.row().prop(props, "render_path", text='')

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
    bl_label = "Models"
    #bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        props = context.scene.reliveBatch
        col = self.layout.column()

        col.label(text="Presets:")
        col.row().operator('opr.set_batch_view_layers', text='All models').preset = 'all_models'
        
        row1 = col.row()
        row1.operator('opr.set_batch_view_layers', text='All (Game)').preset = 'only_game'
        row1.operator('opr.set_batch_view_layers', text='All (FMV)').preset = 'only_fmv'

        row2 = col.row()
        row2.operator('opr.set_batch_view_layers', text='Abe (Game)').preset = 'only_abe_game'
        row2.operator('opr.set_batch_view_layers', text='Abe (FMV)').preset = 'only_abe_fmv'

        col.label(text="View Layers:")
        for i, model in enumerate(context.scene.view_layers):
            col.row().prop(props, "enabled_view_layers", index=i, text=model.name)

        #bool_props = []
        
        # Properties
        #for model in context.scene.view_layers:
        #    model_bool = bpy.props.BoolProperty(name='Include ' + model.name, default=True, description="Include a batch of animations using this model (ViewLayer) when rendering")
        #    bool_props.append(model_bool)
        
        #for bool in bool_props:
        #    col.row().prop(bool)


class ReliveBatchRendererAnimationsPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer_animations"
    bl_parent_id = "VIEW3D_PT_batch_renderer"
    bl_label = "Animations"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        props = context.scene.reliveBatch
        col = self.layout.column()

        # Properties
        col.row().prop(props, "use_custom_csv")
        col.row().label(text="CSV File:")
        if props.use_custom_csv:
            col.row().prop(props, "custom_csv_path", text='')
        else:
            col.row().label(text=get_default_csv(props.character_type))

class ReliveBatchRendererReferencesPanel(ReliveBatchRendererPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_batch_renderer_references"
    bl_parent_id = "VIEW3D_PT_batch_renderer"
    bl_label = "References"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        props = context.scene.reliveBatch
        col = self.layout.column()

        # Properties
        col.row().prop(props, "camera_name")
        col.row().prop(props, "rig_name")
        

# == MAIN ROUTINE

CLASSES = [
    ReliveBatchProperties,
    
    ReliveSetModelsOperator,
    ReliveBatchRenderOperator,
    ReliveBatchCancelOperator,

    ReliveBatchRendererMainPanel,
    ReliveBatchRendererModelsPanel,
    ReliveBatchRendererAnimationsPanel,
    ReliveBatchRendererReferencesPanel,
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