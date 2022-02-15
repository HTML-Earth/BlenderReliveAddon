import bpy, os, csv, re
from pathlib import Path
from shutil import copyfile
from collections import namedtuple

# Animation info collected from each row in csv file
NewAnim = namedtuple('NewAnim', 'name frame_count size_w size_h offset_x offset_y')

newAnims = []
newAnims.append(NewAnim("Mudokon_Chant", 10, 81, 136, 31, 118))
newAnims.append(NewAnim("Mudokon_ChantEnd", 3, 76, 136, 31, 118))

# Rename actions
nameconversions = []

#with open('conversion.txt') as f:
#    lines = f.readlines()

#    for line in lines:
#        pattern = '(.*) -> (.*)'
#        match = re.search(pattern, line) 

#        if match:
#            nameconversions.append (match.group(1), match.group(2))

with open('ban_old_new.tsv') as f:
    lines = f.readlines()
    hits = 0

    for line in lines:
        names = line.split('\t')
        if len(names[1]) > 1 and len(names[2]) > 1 and '#' not in names[1]:

            if names[1] in bpy.data.actions:
                #print(names[1] + " --> " + names[2])
                bpy.data.actions[names[1]].name = names[2].split('\n')[0]
                hits += 1
            else:
                print(names[1] + " not found")


    print("animations renamed: " + str(hits))

# Hide old collections
#oldCollection = bpy.data.collections.new("OldRefs")
#bpy.context.scene.collection.children.link(oldCollection)

#for oldRef in referencesCollection.children:
#    if oldRef.name != "OldRefs":
#        referencesCollection.children.unlink(oldRef)
#        oldCollection.children.link(oldRef)

#bpy.context.view_layer.layer_collection.children['OldRefs'].exclude = True

#for newAnim in newAnims:
#    collection = bpy.data.collections.new(newAnim.name)
#    referencesCollection.children.link(collection)