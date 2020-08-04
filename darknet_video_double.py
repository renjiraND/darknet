from darknet_config import *
from ctypes import *
import os
import time
from nms import nms, fast
import darknet
from utils import *
import statistics

print(darknet.__file__)

netMain = None
metaMain = None
altNames = None

def YOLO():
    global metaMain, netMain, altNames, imageSize, fileName

    print("Network Size:", netSize)

    # only for linux, uncomment if on windows and change config directly
    changeWidth = "sed -i 's/width=[[:digit:]]\+/width=" + str(netSize) + "/g' " + configPath
    changeHeight = "sed -i 's/height=[[:digit:]]\+/height=" + str(netSize) + "/g' " + configPath
    content = os.popen(changeWidth).read()
    content = os.popen(changeHeight).read()

    if not os.path.exists(configPath):
        raise ValueError("Invalid config path `" +
                         os.path.abspath(configPath)+"`")
    if not os.path.exists(weightPath):
        raise ValueError("Invalid weight path `" +
                         os.path.abspath(weightPath)+"`")
    if not os.path.exists(metaPath):
        raise ValueError("Invalid data file path `" +
                         os.path.abspath(metaPath)+"`")
    if netMain is None:
        netMain = darknet.load_net_custom(configPath.encode(
            "ascii"), weightPath.encode("ascii"), 0, 1)  # batch size = 1
    if metaMain is None:
        print(metaPath.encode("ascii"))
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
    
    # use webcam
    # cap = WebcamVideoCapture().start()

    # use video file
    # cap = FileVideoCapture2(path=fileName).start()
    
    #use video file, fastest on gpu
    cap = cv2.VideoCapture(fileName)

    # write to out format, videowriter(filename, codec[only "mp4v" available], fps, size)
    out = cv2.VideoWriter("out-"+fileName, cv2.VideoWriter_fourcc(*"mp4v"), 30.0, imageSize)
    
    print("Starting the YOLO loop...")

    # Create an image we reuse for each detect
    darknet_image = darknet.make_image(darknet.network_width(netMain),darknet.network_height(netMain),3)
    darknet_image_long = darknet.make_image(darknet.network_width(netMain),darknet.network_height(netMain),3)
    ret = 1
    fpslist = []
    ret, frame_read = cap.read()
    while ret:
        prev_time = time.time()

        # get frame with color format
        frame_rgb = cv2.cvtColor(frame_read, cv2.COLOR_BGR2RGB)

        x1,y1,x2,y2 = getCropPoints()

        # crop frame for 2nd yolo
        frame_cropped = np.array(frame_rgb)[y1:y2,x1:x2]
        # resize images for darknet
        frame_resized = cv2.resize(frame_rgb,
                                    (darknet.network_width(netMain),
                                    darknet.network_height(netMain)),
                                    interpolation=cv2.INTER_LINEAR)

        # resize for cropped frame
        frame_resized_cropped = cv2.resize(frame_cropped,
                                    (darknet.network_width(netMain),
                                    darknet.network_height(netMain)),
                                    interpolation=cv2.INTER_LINEAR)

        darknet.copy_image_from_bytes(darknet_image,frame_resized.tobytes())
        darknet.copy_image_from_bytes(darknet_image_long,frame_resized_cropped.tobytes())

        image = doubleDetect(darknet_image, darknet_image_long,frame_rgb)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        fps = (1/(time.time()-prev_time))
        cv2.putText(image, str(int(fps))+"fps", (20,20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, [255,255,0], 2 )
        out.write(image)
        fpslist.append(fps)
        print(fps)
        ret, frame_read = cap.read()

        # for showing webcam
        # cv2.imshow('Demo', image)
        # cv2.waitKey(1)
    print(statistics.mean(fpslist))
    
    # cap.stop()
    cv2.destroyAllWindows()
    out.release()

def doubleDetect(darknet_image, darknet_image_long, frame_rgb):
    global netMain, metaMain
    detections = []
    nmsdet = []

    # Sequential Processing
    # run detections
    nmsdet += detect(netMain, metaMain, darknet_image, 0)
    detections += detect(netMain, metaMain, darknet_image_long, 1)
    
    # convert detections to numpy array
    if len(detections):
        dets = np.array(detections)
        # run non maximum supression to eliminate overlapping bounding boxes
        # returns indexes
        idx = nms.boxes(dets[:,:4], dets[:,-1:], nms_algorithm=fast.nms)
        # get best bounding boxes from nms
        for i in idx:
            nmsdet.append(detections[i])
            
    # draw all bounding boxes
    image = cvDrawBoxes(nmsdet, img=frame_rgb, color="g")
    # image = cvDrawBoxes(detections, img=frame_rgb, color="r")

    return image

def detect(netMain, metaMain, darknet_image, pid):
    global imageSize
    # detect with darknet library
    det = darknet.detect_image(netMain, metaMain, darknet_image, thresh=0.5)
    if pid: # pid 1 means 2nd process
        x1,y1,x2,y2 = getCropPoints()
        det = relabelBBox(det, offsetX=x1,offsetY=y1, imageSize=cropSize)
    else: # 1st iteration
        det = relabelBBox(det, imageSize=imageSize)
    return det


if __name__ == "__main__":
    YOLO()
