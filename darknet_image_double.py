from darknet_config import *
from ctypes import *
import glob
import time
from nms import nms
import darknet
from utils import *
from multiprocessing import Process, Queue
import json

netMain = None
netSecondary = None
metaMain = None
altNames = None

def YOLO():
    global metaMain, netMain, netSecondary, altNames, imageSize

    if not os.path.exists(configPath):
        raise ValueError("Invalid config path `" +
                         os.path.abspath(configPath)+"`")
    
    changeNetSize(netSize, configPath)
    if USE_MULTI:
        changeNetSize(net2Size, config2Path)
        if not os.path.exists(config2Path):
            raise ValueError("Invalid config path `" + os.path.abspath(config2Path)+"`")

    if not os.path.exists(weightPath):
        raise ValueError("Invalid weight path `" +
                         os.path.abspath(weightPath)+"`")
    if USE_TWO_WEIGHT:
        if not os.path.exists(weight2Path):
            raise ValueError("Invalid weight path `" + os.path.abspath(weight2Path)+"`")

    if not os.path.exists(metaPath):
        raise ValueError("Invalid data file path `" +
                         os.path.abspath(metaPath)+"`")
    if netMain is None:
        netMain = darknet.load_net_custom(configPath.encode(
            "ascii"), weightPath.encode("ascii"), 0, 1)  # batch size = 1
    
    if netSecondary is None:
        if USE_TWO_WEIGHT:
            netSecondary = darknet.load_net_custom(config2Path.encode("ascii"), weight2Path.encode("ascii"), 0, 1)
        else:
            netSecondary = darknet.load_net_custom(config2Path.encode("ascii"), weightPath.encode("ascii"), 0, 1)

    if metaMain is None:
        # print(metaPath.encode("ascii"))
        metaMain = darknet.load_meta(metaPath.encode("ascii"))
    if altNames is None:
        try:
            with open(metaPath) as metaFH:
                metaContents = metaFH.read()
                import re
                match = re.search("names *= *(/content/gdrive/My Drive/.*)$", metaContents,
                                  re.IGNORECASE | re.MULTILINE)
                if match:
                    result = match.group(1)
                else:
                    result = None
                try:
                    if os.path.exists(result):
                        with open(result) as namesFH:
                            namesList = namesFH.read().strip().split("\n")
                            altNames = [x.strip() for x in namesList]
                except TypeError:
                    pass
        except Exception:
            pass
    
    data_path = 'data/img-test/'
    detection_path= 'data/detection/'
    class_name = 'pedestrian'
    file_names = [os.path.splitext(os.path.basename(x))[0] for x in glob.glob(data_path + '*.jpg')]
    os.makedirs(os.path.dirname(detection_path), exist_ok=True)

    print("Starting the YOLO loop...")

    # Create an image we reuse for each detect
    darknet_image = darknet.make_image(darknet.network_width(netMain),darknet.network_height(netMain),3)
    darknet_image_crop = darknet.make_image(darknet.network_width(netMain),darknet.network_height(netMain),3)
    prev_time = time.time()
    
    for file_name in file_names:
        ped = cv2.imread(data_path+file_name+'.jpg')

        ped_h, ped_w = ped.shape[:2]
        imageSize = (ped_w,ped_h)
        print(imageSize)

        crop_y1,crop_y2,crop_x1,crop_x2 = getCropPoints()

        frame_rgb = cv2.cvtColor(ped, cv2.COLOR_BGR2RGB)
        frame_cropped = np.array(frame_rgb,)
        frame_cropped = np.array(frame_cropped[crop_y1:crop_y2,crop_x1:crop_x2])
        # cv2.imshow("test", frame_cropped)
        # cv2.waitKey(0)
        
        frame_resized_cropped = cv2.resize(frame_cropped,
                                    (darknet.network_width(netMain),
                                    darknet.network_height(netMain)),
                                    interpolation=cv2.INTER_LINEAR)

        frame_resized = cv2.resize(frame_rgb,
                                    (darknet.network_width(netMain),
                                    darknet.network_height(netMain)),
                                    interpolation=cv2.INTER_LINEAR)

        darknet.copy_image_from_bytes(darknet_image,frame_resized.tobytes())
        darknet.copy_image_from_bytes(darknet_image_crop,frame_resized_cropped.tobytes())

        image,dets = doubleDetect(darknet_image, darknet_image_crop,frame_rgb)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        # cv2.rectangle(image, (crop_x1,crop_y1), (crop_x2,crop_y2), (255, 255, 255), 2)
        

        fps = (1/(time.time()-prev_time))
        out = cv2.imwrite('output.jpg',image)
        print("speed:", round(fps,3), "frame per second")
        # cv2.imshow("demo",image)
        # cv2.waitKey(0)

        # TODO: change data path to another folder
        if len(dets):
            with open(detection_path+file_name+'.txt','w') as f:
                for det in dets:
                    x,y,w,h,prob = det
                    x1,y1,x2,y2 = convertBack(x,y,w,h)
                    f.write('{} {} {} {} {} {}\n'.format(class_name, prob, x1,y1,x2,y2))
                f.close()

def doubleDetect(darknet_image, darknet_image_crop, frame_rgb):
    global netMain, metaMain
    detections = []
    nmsdet = []
# Sequential processing
    detections += detect_sequential(netSecondary, metaMain, darknet_image, 0)
    # image = cvDrawBoxes(detections, img=frame_rgb, color="r")
    if USE_MULTI:
        detections += detect_sequential(netMain, metaMain, darknet_image_crop, 1)
    else:
        detections += detect_sequential(netMain, metaMain, darknet_image_crop, 1)
    dets = np.array(detections)
    if len(dets) > 0:
        boxes = dets[:,:4]
        scores = dets[:,-1:]
        idx = nms.boxes(boxes, scores, nms_algorithm=nms.fast.nms)
        for i in idx:
            nmsdet.append(detections[i])
    # print("detection done in:",round(finish-start, 3),"s")

    # image = cvDrawBoxes(dets, img=frame_rgb, color="r")
    image = cvDrawBoxes(nmsdet, img=frame_rgb, color="g")

    return image,np.array(dets)

def detect_sequential(network, metaMain, darknet_image, pid):
    global imageSize
    crop_y1,crop_y2,crop_x1,crop_x2 = getCropPoints()
    det = darknet.detect_image(network, metaMain, darknet_image, thresh=0.5, nms=0)
    if pid:
        det = relabelBBox(det, offsetX=crop_x1, \
        offsetY=crop_y1, imageSize=cropSize)
    else:
        det = relabelBBox(det, imageSize=imageSize)
    return det

if __name__ == "__main__":
    YOLO()
