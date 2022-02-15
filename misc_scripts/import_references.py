import bpy, os, csv
from pathlib import Path
from shutil import copyfile
from collections import namedtuple

# Animation info collected from each row in csv file
NewAnim = namedtuple('NewAnim', 'name frame_count size_w size_h offset_x offset_y')

newAnims = []
newAnims.append(NewAnim("Mudokon_Chant", 10, 81, 136, 31, 118))
newAnims.append(NewAnim("Mudokon_ChantEnd", 3, 76, 136, 31, 118))

# Create ref collections
referencesCollection = bpy.data.collections.new("References")
bpy.context.scene.collection.children.link(referencesCollection)
referencesCollection.color_tag = 'COLOR_01'
referencesCollection.hide_select = True

# Add all reference image sequences
for newAnim in newAnims:
    # load image and set to sequence
    img = bpy.data.images.load("//sprites/" + newAnim.name + "/0.png")
    img.name = newAnim.name
    img.source = 'SEQUENCE'

    # create new empty
    empty = bpy.data.objects.new(newAnim.name, None)

    # set empty to use image sequence
    empty.empty_display_type = 'IMAGE'
    empty.data = img
    
    # set sequence frames
    #   for some reason the frame count starts at 0
    #   and the first frame starts at 1... Blender pls
    empty.image_user.frame_duration = newAnim.frame_count - 1
    empty.image_user.frame_start = 1

    # enable alpha
    empty.use_empty_image_alpha = True

    # set size depending on aspect ratio
    if newAnim.size_w > newAnim.size_h:
        empty.empty_display_size = newAnim.size_w * 0.017
    else:
        empty.empty_display_size = newAnim.size_h * 0.017

    # x offset (flipped)
    empty.empty_image_offset[0] = 1 - (newAnim.offset_x / newAnim.size_w) - 1
    # y offset (not flipped)
    empty.empty_image_offset[1] =     (newAnim.offset_y / newAnim.size_h) - 1

    # rotate toward camera
    empty.rotation_euler[0] = 1.5708
    empty.rotation_euler[2] = -1.5708

    # add to collection
    referencesCollection.objects.link(empty)
