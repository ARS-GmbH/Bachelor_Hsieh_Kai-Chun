"""
Copyright (c) 2020 ARS Computer & Consulting GmbH

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
"""

import os, subprocess, io
import cv2
import numpy as np
from matplotlib import pyplot as plt


def getFileList(directory, extension = "bmp"):
    names = []
    
    for filename in os.listdir(directory):
        processedFilename = os.path.join(directory, filename.lower())
        
        if processedFilename.endswith(extension): 
            names.append(processedFilename)
            
    return names
    
def getDirectShowDevices(ffmpegPath):
    cameraInfo = subprocess.run(
        [ffmpegPath, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummyffmpeg"], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE)

    #print(cameraInfo.returncode)

    outputStream = io.BytesIO(cameraInfo.stderr)
    output = outputStream.readline()

    while len(output) > 0:
        trimedOutput = output.decode().strip()
        if trimedOutput.startswith("[dshow @"):
            print(trimedOutput)
        
        output = outputStream.readline()

def showOpenCVImage(openCVImage, title = None, cols = 1):

    fig = plt.figure()
    a = fig.add_subplot(cols, 1.0, 1)
    if openCVImage.ndim == 2:
        plt.gray()
    plt.imshow(cv2.cvtColor(openCVImage, cv2.COLOR_BGR2RGB))

    if title is not None:
        a.set_title(title)

    fig.set_size_inches(np.array(fig.get_size_inches()))
    plt.show()