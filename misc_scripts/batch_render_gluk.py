# the basic framework for this was nicked from:
# https://blender.stackexchange.com/questions/71454/is-it-possible-to-make-a-sequence-of-renders-and-give-the-user-the-option-to-can

import bpy, os, csv
from pathlib import Path
from shutil import copyfile
from collections import namedtuple

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

class Multi_Render(bpy.types.Operator):
    """Docstring"""
    bl_idname = "render.multi"
    bl_label = "Render multiple times"

    _timer = None
    _timer_interval = 0.1
    
    frames_to_render = []
    frames_to_copy = []

    stop = None
    rendering = None

    camera_name = 'Camera'
    rig_name = 'rig'
    ref_pose_name = '_REF'

    default_render_path = '//renders/_untitled'
    csv_path = 'gluk_animlist.csv'

    default_resolution_x = 151
    default_resolution_y = 254
    default_camera_scale = 3.364
    default_camera_y_pos = 0.275
    
    # model types
    all_model_types = ['rf_exec_blue', 'rf_exec_brown', 'rf_exec_green', 'rf_exec_greyblue', 'rf_exec_purple', 'rf_exec_red', 'jr_exec', 'aslik', 'dripik', 'menu']
    
    # models (view layers)
    models_all = ['rf_exec_blue', 'rf_exec_brown', 'rf_exec_green', 'rf_exec_greyblue', 'rf_exec_purple', 'rf_exec_red', 'jr_exec', 'jr_exec_gib', 'aslik', 'aslik_gib', 'dripik', 'dripik_gib', 'dripik_menu']
    models_rf_exec_fmv_green = ['rf_exec_green']
    models_rf_exec_fmv_all = ['rf_exec_blue', 'rf_exec_brown', 'rf_exec_green', 'rf_exec_greyblue', 'rf_exec_purple', 'rf_exec_red']
    models_jr_exec_game = ['jr_exec', 'jr_exec_gib']
    models_aslik_fmv = ['aslik', 'aslik_gib']
    models_dripik_fmv = ['dripik', 'dripik_gib']
    models_menu_dripik = ['dripik_menu']
    
    def get_model_type(self, model):
        for model_type in self.all_model_types:
            if model_type in model:
                return model_type

    def check_model(self, model):
        if model in self.models_all: # change this to only render select models
            return True
        return False

    # Parses string and returns list of FrameInfos
    def get_frame_list(self, frame_string):
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

    def copy_duplicate_frames(self):
        print('COPYING DUPLICATE FRAMES...')
        for dupe in self.frames_to_copy:
            src = os.path.realpath(bpy.path.abspath('{}.png'.format(dupe[0])))
            dst = os.path.realpath(bpy.path.abspath('{}.png'.format(dupe[1])))

            #print('source: {}\ndestination: {}'.format(src, dst))
            if not os.path.isdir(os.path.dirname(dst)):
                os.mkdir(os.path.dirname(dst))

            print('COPYING {} TO {}'.format(src, dst))
            copyfile(src, dst)

    def get_action(self, action_name):
        # Check all available actions
        for action in  bpy.data.actions:
            # Check if action has correct name
            if action.name == action_name:
                return action
            
        print('Action: {} not available'.format(action_name))
        return None
    
    def apply_action(self, action):
        bpy.context.scene.objects[self.rig_name].animation_data.action = action
    
    def calculate_cam_scale(self, width, height):
        if height == 254:
            return 0.013244 * height
        
        return 0.01682 * height
        
    def calculate_cam_y(self, width, height):
        if height == 254:
            return 0.5 - (57 / height)
    
        if height == 140:
            return 0.5 - (22 / height)
        
        if height == 120:
            return 0.5 - (25 / height)
        
        return 0.5 - (45 / height)
    
    def pre(self, *args, **kwargs):
        self.rendering = True

    def post(self, *args, **kwargs):
        self.frames_to_render.pop(0)
        self.rendering = False
        
        if len(self.frames_to_render) < 1:
            print("DONE")
            self.finished()

    def cancelled(self, *args, **kwargs):
        self.stop = True
        print("CANCELLED")
        self.finished()
        
    def finished(self):
        # COPY DUPLICATE FRAMES
        self.copy_duplicate_frames()

        # RESET FILEPATH
        bpy.context.scene.render.filepath = self.default_render_path
        
        # RESET ANIMATION
        bpy.context.scene.objects[self.rig_name].animation_data.action = bpy.data.actions[self.ref_pose_name]
        
        # RESET FRAME 
        # causes crash :(
        #bpy.context.scene.frame_set(0)

        # RESET RESOLUTION
        bpy.context.scene.render.resolution_x = self.default_resolution_x
        bpy.context.scene.render.resolution_y = self.default_resolution_y
        
        # RESET CAMERA
        bpy.data.cameras[self.camera_name].ortho_scale = self.default_camera_scale
        bpy.data.cameras[self.camera_name].shift_y     = self.default_camera_y_pos

    def execute(self, context):
        self.stop = False
        self.rendering = False
        
        # Gather all frames from csv into collection
        with open(self.csv_path) as csvfile:
            rdr = csv.reader(csvfile)
            for i, row in enumerate( rdr ):
                if i == 0:
                    continue
                
                # create AnimInfo from current row
                anim = AnimInfo(row[0], row[1], int(row[2]), int(row[3]), row[4])
                
                # check if model is available (usually model TYPE, but for glukkons it represents a single model)
                if not self.check_model(anim.model_type):
                    print('Model: {} not available'.format(anim.model_type))
                    continue
                
                # parse frame string to get list of frames
                frame_list = self.get_frame_list(anim.frame_string)

                # for each frame in frame list
                for frame_info in frame_list:
                    # get action handle from action name
                    action = self.get_action(frame_info.action_name)
                    # if action is not null
                    if not action == None:
                        # assume that the frame is unique
                        unique = True

                        # make relative path string
                        file_path = Path('renders/{}/{}/{}_{}'.format(self.get_model_type(anim.model_type), anim.id.split('_')[0], anim.id, frame_info.index))

                        for prev_frame in self.frames_to_render:
                            # if frame already in self.frames_to_render
                            if prev_frame.action == action and prev_frame.action_frame == frame_info.action_frame and prev_frame.model == anim.model_type and prev_frame.width == anim.width and prev_frame.height == anim.height:
                                # frame is no longer considered unique
                                unique = False
                                # add frame to frames_to_copy instead
                                self.frames_to_copy.append((prev_frame.file_path, file_path))
                                print('{} will be copied to {}'.format(prev_frame.file_path, file_path))
                                break

                        if unique:
                            # Add frame to frames_to_render
                            self.frames_to_render.append(RenderFrame(anim.id, frame_info.index, anim.width, anim.height, action, frame_info.action_frame, anim.model_type, file_path))
                    
        context.scene.render.filepath = self.default_render_path

        bpy.app.handlers.render_pre.append(self.pre)
        bpy.app.handlers.render_post.append(self.post)
        bpy.app.handlers.render_cancel.append(self.cancelled)

        # The timer gets created and the modal handler
        # is added to the window manager
        self._timer = context.window_manager.event_timer_add(self._timer_interval, window=context.window)
        context.window_manager.modal_handler_add(self)

        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == 'TIMER': # This event is signaled every _timer_interval seconds
                                  # and will start the render if available

            # If cancelled or no more frames to render, finish.
            if True in (not self.frames_to_render, self.stop is True):

                # We remove the handlers and the modal timer to clean everything
                bpy.app.handlers.render_pre.remove(self.pre)
                bpy.app.handlers.render_post.remove(self.post)
                bpy.app.handlers.render_cancel.remove(self.cancelled)
                context.window_manager.event_timer_remove(self._timer)

                return {"FINISHED"}

            elif self.rendering is False: # Nothing is currently rendering.
                                          # Proceed to render.
                sc = context.scene
                
                # retrieve frame data
                frame = self.frames_to_render[0]
                
                # Apply action
                self.apply_action(frame.action)
                
                # Set current frame
                sc.frame_set(frame.action_frame)
                
                # Set output resolution
                sc.render.resolution_x = frame.width
                sc.render.resolution_y = frame.height
                
                # Setup camera position and scale
                bpy.data.cameras[self.camera_name].ortho_scale = self.calculate_cam_scale(frame.width, frame.height)
                bpy.data.cameras[self.camera_name].shift_y     = self.calculate_cam_y    (frame.width, frame.height)

                # Set file path
                sc.render.filepath = '//{}'.format(frame.file_path)

                # Render frame
                bpy.ops.render.render("INVOKE_DEFAULT", layer=frame.model, write_still=True)

        return {"PASS_THROUGH"}

def register():
    bpy.utils.register_class(Multi_Render)

def unregister():
    bpy.utils.unregister_class(Multi_Render)

if __name__ == "__main__":
    register()

    bpy.ops.render.multi()