# -*- coding: utf-8 -*-
"""
Created on Tue Mar 14 09:59:53 2017

@author: SzMike
"""

import os
import skimage.io as io
io.use_plugin('pil') # Use only the capability of PIL
from matplotlib.path import Path
import numpy as np
import matplotlib.pyplot as plt
from csv import DictWriter


import annotations
import diagnostics
import imtools
import cfg
import detections
import cv2

def rotate(image, angle, center = None, scale = 1.0):
    (h, w) = image.shape[:2]

    if center is None:
        center = (w / 2, h / 2)

    # Perform the rotation
    M = cv2.getRotationMatrix2D(center, angle, scale)
    rotated = cv2.warpAffine(image, M, (w, h))

    return rotated

#onedrive_user='SzMike'
onedrive_user='picturio'
output_base_dir=os.path.join(r'C:\Users',onedrive_user,'OneDrive\WBC\DATA')
image_dir=os.path.join(output_base_dir,'Annotated')
output_dir=os.path.join(output_base_dir,'Detected_Cropped')
#mask_dir=os.path.join(output_base_dir,'Mask')

#image_dir=r'd:\Projects\WBC\data\Test'
#output_dir=r'd:\Projects\WBC\diag'


plt.ioff()

param=cfg.param()
wbc_types=param.wbc_types

rot_angles=[0,90,180,270]

image_list_indir=imtools.imagelist_in_depth(image_dir,level=1)
print('processing '+str(len(image_list_indir))+' images')

i_detected=-1
samples=[]
for i, image_file in enumerate(image_list_indir):
    print(str(i)+' : '+image_file)
    """
    READ IMAGE
    """
    # READ THE IMAGE
    im = io.imread(image_file) # read uint8 image
   
    """ 
    CREATE AND SAVE DIAGNOSTICS
    """
    diag=diagnostics.diagnostics(im,image_file,vis_diag=False)

    wbc_types=diag.param.wbc_types
    wbc_basic_types=diag.param.wbc_basic_types
   
    """
    CREATE HSV
    """
    hsv_resize, scale=imtools.imRescaleMaxDim(diag.hsv_corrected,diag.param.middle_size,interpolation = 0)
    im_resize, scale=imtools.imRescaleMaxDim(diag.im_corrected,diag.param.middle_size,interpolation = 0)
    """
    WBC nucleus masks
    """    
    sat_tsh=max(diag.sat_q95,diag.param.wbc_min_sat)
    mask_nuc=detections.wbc_nucleus_mask(hsv_resize,diag.param,sat_tsh=sat_tsh,scale=scale,vis_diag=False,fig='')
   
    """
    CREATE WBC REGIONS
    """    
    prop_wbc=detections.wbc_regions(mask_nuc,diag.param,scale=scale)
    
    """
    SAVE NUCLEUS MASK
    """
#    mask_file_name=str.replace(image_file,image_dir,mask_dir)
#    if not os.path.isdir(os.path.dirname(mask_file_name)):
#        os.makedirs(os.path.dirname(mask_file_name))
#    io.imsave(mask_file_name,255*mask_nuc)

    """
    PARAMETERS for WBC NORMALIZATION 
    """
    if mask_nuc.sum()>0:
        pixs=im_resize[mask_nuc,]
        diag.measures['nucleus_median_rgb']=np.median(pixs,axis=0)
    else:
        continue

    """
    READ manual annotations
    """ 
    head, tail=os.path.splitext(image_file)
    xml_file_1=head+'.xml'
    if os.path.isfile(xml_file_1):
        try:
            xmlReader = annotations.AnnotationReader(xml_file_1)
            annotations_bb=xmlReader.getShapes()
        except:
            annotations_bb=[]
            continue
    else:
        annotations_bb=[]
        continue   
    # keep WBC detections    
    annotations_bb = [bb for bb in annotations_bb if bb[0] in list(wbc_types.keys())]

    """
    CREATE WBC shapelist 
    """

    shapelist_WBC=[]
    for p in prop_wbc:
        # centroid is in row,col
         pts=[(p.centroid[1]/scale+0.8*p.major_axis_length*np.cos(theta*2*np.pi/20)/scale,p.centroid[0]/scale+0.8*p.major_axis_length*np.sin(theta*2*np.pi/20)/scale) for theta in range(20)] 
         #pts=[(p.centroid[1]/scale,p.centroid[0]/scale)]
         one_shape=('un','circle',pts,'None','None')
         
         # Do NOT CROP BB-s, which have parts outside the image
         if min((im.shape[1],im.shape[0])-np.max(one_shape[2],axis=0))<0\
                or min(np.min(one_shape[2],axis=0))<0:
            continue
         
         shapelist_WBC.append(one_shape)    
    
    shapelist=shapelist_WBC
    """
    REMOVE ANNOTATIONS CLOSE TO BORDER
    """
    shapelist=annotations.remove_border_annotations(shapelist,im.shape,diag.param.border)

    """
    CROP DETECTIONS
    """
    for one_shape in shapelist:
        
        mins=(np.min(one_shape[2],axis=0)*scale).astype('int32')
        maxs=(np.max(one_shape[2],axis=0)*scale).astype('int32')
        o=(mins+maxs)/2
        r=(maxs-mins)/2
          
        if max(o-np.sqrt(2)*r)>0 and sum(o[::-1]+np.sqrt(2)*r<im.shape[:-1])==2:
        # sqrt(2) is used here assuring rotation=45
            is_pos_detect=False
            i_detected+=1
            # centroid is in row,col
            o=np.average(one_shape[2],axis=0)
            for alpha in rot_angles:
            
                im_rotated=rotate(diag.im_corrected,alpha,center=(o[0],o[1]))
                im_cropped,o,r=imtools.crop_shape(im_rotated,one_shape,\
                                                    diag.param.rgb_norm,diag.measures['nucleus_median_rgb'],\
                                                    scale=1,adjust=True)
            
                if im_cropped is not None and r[0] > diag.param.rbcR*1.5:
                    
                    wbc_type='un'
                    for each_bb in annotations_bb:
            #            if each_bb[0] in list(wbc_types.keys()):
                            # only if in wbc list to be detected
                        bb=Path(np.array(each_bb[2]))
                        intersect = bb.contains_point(np.asarray(o)) 
                        if intersect>0:
                            # automatic detection is within manual annotation
                            is_pos_detect=True
                            if each_bb[0] in list(wbc_types.keys()):
                                wbc_type=diag.param.wbc_type_dict[each_bb[0]]
                            if wbc_type not in list(wbc_basic_types.keys()):
                                wbc_type='un' # unknown
                                break
                    
                   
                    # SAVE    
                    crop_file=os.path.join(output_dir,wbc_type+'_'+str(i_detected)+'_'+str(alpha)+'.png')
                    io.imsave(crop_file,im_cropped)
                    
                    sample={'im':os.path.basename(image_file),'crop':os.path.basename(crop_file),\
                            'rotation':alpha,
                            'rbcR':diag.param.rbcR,'wbc':wbc_type,\
                            'origo':np.asarray(o),'radius':r,\
                            'sat_tsh':diag.measures['saturation_q95'],\
                            'nucleus_median_rgb':diag.measures['nucleus_median_rgb']}
                    samples.append(sample)
            
keys = samples[0].keys()
with open(os.path.join(output_dir,'detections.csv'), "w", newline='') as f:
    dict_writer = DictWriter(f, keys, delimiter=";")
    dict_writer.writeheader()
    for sample in samples:
        dict_writer.writerow(sample)