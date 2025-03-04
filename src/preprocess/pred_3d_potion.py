from utils_3d import *
from config import configs

'''
Multiprocessing pool to fully utillize 8 cores 
'''
def potion_worker(nSamples):
    print(nSamples)
    # load annotations and predictions
    path_crn_label=os.path.join(path_labels,all_labels[nSamples])
    path_crn_preds=os.path.join(path_preds,all_preds[nSamples])
    crn_label=sio.loadmat(path_crn_label) # store the label, isTrain, bboxes
    crn_preds=h5py.File(path_crn_preds)  # dictionary, filename is the key. each value is an array of shape 16x3 

    # get isTrain, bounding box, label, #frames
    bboxes=crn_label['bbox'].astype(np.int32)
    
    # keys of the crn_preds
    all_keys=sorted(crn_preds.keys())
    each_label=all_labels[nSamples].split('.')[0]
    path=os.path.join(PATH_OUTPUT,each_label+'.npy')
    if(bboxes.shape[0]==len(all_keys) and os.path.exists(path)==False): # in some cases, there are mismatching and is wired

        # get global bounding box
        dimensions =crn_label["dimensions"][0][:2]
        global_min_x = max(0, min(bboxes[:, 0] - EDGE))
        global_min_y = max(0, min(bboxes[:, 1] - EDGE))

        # transform each frame within the same video to the global coordinate system
        nFrames=len(all_keys)
        joints_x=np.zeros((nFrames,NUM_JOINT))
        joints_y=np.zeros((nFrames,NUM_JOINT))
        joints_z=np.zeros((nFrames,NUM_JOINT))
        for nframe in range(nFrames):
            crn_joints=np.array(crn_preds[all_keys[nframe]]).astype(np.float32) # 16x3 array
            # get transformation scale and shifts along x and y axis
            shift_x = 0
            shift_y = 0
            min_x = max(0, bboxes[nframe, 0] - EDGE)
            min_y = max(0, bboxes[nframe, 1] - EDGE)
            max_x = min(bboxes[nframe, 2] + EDGE, dimensions[1])
            max_y = min(bboxes[nframe, 3] + EDGE, dimensions[0])
            h = max_y - min_y
            w = max_x - min_x
            size = max(h, w)
            scale = size / OutputRes
            paddings = int(abs(h - w) / 2)
            if h >= w:
                shift_x -= paddings
            else:
                shift_y -= paddings

            left = min_x - global_min_x
            upper = min_y - global_min_y

            shift_x += left
            shift_y += upper

            # apply transformations 0:along horizontal x     1: along vertical y
            crn_joints*=scale
            crn_joints[:,0]+=shift_x
            crn_joints[:,1]+=shift_y
            

            joints_x[nframe]=crn_joints[:,0]
            joints_y[nframe]=crn_joints[:,1]
            joints_z[nframe]=crn_joints[:,2]

        # normalize the joints to the desired FRAME_SIZE and FRAME_SIZE of the heatmap
        min_joints_x=np.min(joints_x)-5
        min_joints_y=np.min(joints_y)-5
        min_joints_z=np.min(joints_z)-5
        max_joints_x=np.max(joints_x)+5
        max_joints_y=np.max(joints_y)+5
        max_joints_z=np.max(joints_z)+5

        scale_x=FRAME_SIZE/(max_joints_x-min_joints_x)
        scale_y=FRAME_SIZE/(max_joints_y-min_joints_y)
        scale_z=FRAME_SIZE/(max_joints_z-min_joints_z)

        min_scale=min(scale_x,scale_y,scale_z)

        normalized_x=(joints_x-min_joints_x)*min_scale
        normalized_y=(joints_y-min_joints_y)*min_scale
        normalized_z=(joints_z-min_joints_z)*min_scale
        
        normalized_x=normalized_x.astype(np.int32)
        normalized_y=normalized_y.astype(np.int32)
        normalized_z=normalized_z.astype(np.int32)
      
        # get heatvolumns
        heatmaps=np.zeros((nFrames,NUM_JOINT,FRAME_SIZE,FRAME_SIZE,FRAME_SIZE))

        # generate ramdom sigma
        rand_amplitudes=randint(33,37,NUM_JOINT*nFrames)/100
        ind=0
        for i in range(nFrames):
            for j in range(NUM_JOINT):
                heatmaps[i,j,:,:,:]=get_heatvolume(rand_amplitudes[ind],normalized_x[i,j],normalized_y[i,j],normalized_z[i,j],FRAME_SIZE)
                ind+=1
        # get descriptor
        descriptor=get_descriptor(heatmaps,C).astype('float32')

        # keras take channel last
        descriptor=np.moveaxis(descriptor,0,-1)
        np.save(path,descriptor)


## define global variables
NUM_JOINT=configs['num_joints']['pred']
EDGE=configs['edge']
OutputRes=256
FRAME_SIZE=configs['frame_size']
C=configs['C']
partition={}
partition['train']=[]
partition['test']=[]
labels={}

## get input and output path
PATH_INPUT=configs['dir_penn_action']
path_labels=os.path.join(PATH_INPUT,'labels')
path_preds=os.path.join(PATH_INPUT,'pred')
all_labels=sorted(os.listdir(path_labels))
all_preds=sorted(os.listdir(path_preds))
assert len(all_labels)==len(all_preds)


PATH_OUTPUT=os.path.join(configs['dir_potion'],'3D-'+str(configs['frame_size']))
if(os.path.exists(PATH_OUTPUT)):
    os.system('rm -r '+PATH_OUTPUT)
os.system('mkdir '+PATH_OUTPUT)
# use multiprocessing pool to get potion representation
p=Pool()
count=0
for cSample in range(len(all_labels)):
    p.apply_async(potion_worker, args=(cSample,))
p.close()
p.join()


## get meta data
for nSamples in range(len(all_labels)):
    path_crn_label=os.path.join(path_labels,all_labels[nSamples])
    path_crn_preds=os.path.join(path_preds,all_preds[nSamples])
    crn_label=sio.loadmat(path_crn_label) # store the label, isTrain, bboxes
    crn_preds=h5py.File(path_crn_preds)  # dictionary, filename is the key. each value is an array of shape 16x3 

    # get isTrain, bounding box, label, #frames
    bboxes=crn_label['bbox'].astype(np.int32)
    label=dict_action[crn_label['action'][0]]
    isTrain=crn_label['train'][0][0]

    # keys of the crn_preds
    all_keys=sorted(crn_preds.keys())

    if(bboxes.shape[0]==len(all_keys)): # in some cases, there are mismatching and is wired
        # save the dictionary
        each_label=all_labels[nSamples].split('.')[0]
        labels[each_label]=label
        if(isTrain==1):
            partition['train'].append(each_label)
        else:
            partition['test'].append(each_label)
        
dir_meta=os.path.join(PATH_OUTPUT,'meta')
if(os.path.exists(dir_meta)):
    os.system('rm -r '+dir_meta)
os.system('mkdir '+dir_meta)        
path=os.path.join(dir_meta,'partition.json')
with open(path,'w') as fp:
    json.dump(partition,fp)

path=os.path.join(dir_meta,'labels.json')
with open(path,'w') as fp:
    json.dump(labels,fp)