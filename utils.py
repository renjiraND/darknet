'''
    Moved utility functions out of darknet_video.py
    original code by AlexeyAB (convertBack, cvDrawBoxes, )
'''

import cv2
import numpy as np
from darknet_config import *
from threading import Thread
from queue import Queue

'''
    Function to Convert xywh to x1y1x2y2 (two points)
'''
def convertBack(x, y, w, h):
    xmin = int(round(x - (w / 2)))
    xmax = int(round(x + (w / 2)))
    ymin = int(round(y - (h / 2)))
    ymax = int(round(y + (h / 2)))
    return xmin, ymin, xmax, ymax


def getCropPoints():
    global imageSize, cropSize, verticalOffset, horizontalOffset
    return \
    int((imageSize[1]-cropSize[1]+verticalOffset)/2),\
    int((imageSize[1]+cropSize[1]+verticalOffset)/2),\
    int((imageSize[0]-cropSize[0]+horizontalOffset)/2),\
    int((imageSize[0]+cropSize[0]+horizontalOffset)/2)

'''
    Function to draw bounding boxes from list of detections
    adapted for double yolo
'''
def cvDrawBoxes(detections, img, color):
    for x, y, w, h, pred in detections:
        xmin, ymin, xmax, ymax = convertBack(x, y, w, h)
        pt1 = (xmin, ymin)
        pt2 = (xmax, ymax)
        cv2.rectangle(img, pt1, pt2, (0, 255, 0) if color == "g" else (255,0,0), 1)
        cv2.putText(img,
                    "peds" +
                    " [" + str(round(pred * 100, 2)) + "]",
                    (pt1[0], pt1[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.3,
                    [0, 255, 0] if color == "g" else [255,0,0], 1)
    return img

'''
    Function to relabel and resize bbox to fit usual image size
'''
def relabelBBox(detections, imageSize, offsetX=0, offsetY=0):
    global netSize
    h_factor, v_factor= (imageSize[0]/netSize),\
                        (imageSize[1]/netSize)
    new_labels = []
    for detection in detections:
        if(detection[0].decode() == "pedestrian"):
            updated_xy = [(detection[2][0]*h_factor)+offsetX, \
                        (detection[2][1]*v_factor)+offsetY, \
                        detection[2][2]*h_factor, \
                        detection[2][3]*v_factor]
            new_labels.append((updated_xy + [detection[1]]))
    return new_labels

'''
    Function to relabel and resize bbox to fit usual image size
'''
def reLabel(label, imageSize, offsetX=0, offsetY=0):
    h_factor, v_factor= (imageSize[0]),\
                        (imageSize[1])
    updated_xy = [(label[0]*h_factor)+offsetX, \
                (label[1]*v_factor)+offsetY, \
                label[2]*h_factor, \
                label[3]*v_factor]
    return updated_xy


'''
    Threading input frames, originally by Adrian Rosebrock
'''
class WebcamVideoCapture:

    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src)
        (self.ret, self.frame) = self.stream.read()

        # auto set video size as original video
        if self.stream.isOpened():
            self.imageSize = (int(self.stream.get(cv2.CAP_PROP_FRAME_WIDTH)), \
                int(self.stream.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            print("video resolution is: ", imageSize[0], "x", imageSize[1])

        self.stopped = False

    def start(self):
        Thread(target=self.update, args=()).start()
        return self
    
    def update(self):
        while not self.stopped:
            (self.ret, self.frame) = self.stream.read()

    def read(self):
        return self.ret, self.frame

    def stop(self):
        self.stopped = True
        self.stream.release()

'''
    Threading for video, originally by Adrian Rosebrock
'''
class FileVideoCapture:
    def __init__(self, path, queueSize=128):
        self.stream = cv2.VideoCapture(path)
        self.stopped = False

        # auto set video size as original video
        if self.stream.isOpened():
            self.imageSize = (int(self.stream.get(cv2.CAP_PROP_FRAME_WIDTH)), \
                int(self.stream.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            print("video resolution is: ", imageSize[0], "x", imageSize[1])

        self.Q = Queue(maxsize=queueSize)

    def start(self):
        t = Thread(target=self.update, args=())
        t.daemon = True
        t.start()
        return self

    def update(self):
        while True:
            if self.stopped:
                return
            
            if not self.Q.full():
                (ret, frame) = self.stream.read()

                if not ret:
                    self.stop()
                    return
                
                self.Q.put((ret, frame))

    def read(self):
        return self.Q.get()

    def more(self):
        return self.Q.qsize() > 0

    def stop(self):
        self.stopped = True
        self.stream.release()