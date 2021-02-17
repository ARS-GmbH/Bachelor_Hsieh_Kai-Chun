"""
Copyright (c) 2020 ARS Computer & Consulting GmbH

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
"""

from . import interface
import cv2
import numpy as np
import time, os

PHOTO_DIRECTORY = "data/mylocalphotoloader"

def reflector():
    return LocalPhotoLoader

class LocalPhotoLoader(interface.ResourceLoader):

    def __init__(self, datatableName, serverAPI):
        self._datatableName = datatableName

        import os
        if not os.path.exists(PHOTO_DIRECTORY):
            os.makedirs(PHOTO_DIRECTORY)

    # getters of basic metadata
    @staticmethod
    def getManufacturer():
        return "edu.hm.hsieh"

    @staticmethod
    def getAuthor():
        return "hsieh"

    @staticmethod
    def getName():
        return "mylocalphotoloader"

    @staticmethod
    def getVersion():
        return "1.0"

    @staticmethod
    def getDescription():
        return "This is a basic photo loader. This loader compress all photo recieving with PNG formate and saves and loads photos directly from local file-system."
    
    @staticmethod
    def getPriceDescription():
        return "1 database operation per photo read/write. Price of storage depends on the size of the photo."

    # service handlers
    # return opencv image
    def getResource(self, database, id):
        session = database.cursor()
        session.execute("SELECT remote_id, extra_info FROM " + self._datatableName + " WHERE id = %s", (id,))
        imageInfo = session.fetchone()
        session.close()

        if imageInfo is None:
            print("INFO (", self._datatableName,") Provided id", id, "is not found in plugin database.")
            return None

        filename, _ = imageInfo
        imagePath = os.path.join("./" + PHOTO_DIRECTORY, filename)

        if not os.path.isfile(imagePath):
            print("INFO (", self._datatableName,") Photo", filename, "can no longer be found from the filesystem.")
            return None

        frame = cv2.imread(imagePath)
        return frame
    
    def getResourceExtraInfo(self, database, id):
        session = database.cursor()
        session.execute("SELECT extra_info FROM " + self._datatableName + " WHERE id = %s", (id,))
        imageInfo = session.fetchone()
        session.close()

        if not imageInfo:
            return None

        return "No Extra Infomation Available."

    def putResource(self, database, id, photoStream, mime):
        if not mime.startswith("image/"):
            print("DEBUG This resource-loader doesn't support ", mime)
            return False

        filename = LocalPhotoLoader.getName() + "-" + str(int(time.time_ns())) + ".png"

        savePhotoResult = photoWriter(os.path.join(PHOTO_DIRECTORY, filename), photoStream)
        if savePhotoResult:
            # update database record
            session = database.cursor()
            session.execute("INSERT INTO " + self._datatableName + " (id, remote_id) VALUES (" + str(id) + ", '" + filename + "');")
            database.commit()

            return True
        
        return False

# return true if ok, false if failed
def photoWriter(filename, photoStream):
    frame = cv2.imdecode(np.fromstring(photoStream.read(), np.uint8), cv2.IMREAD_COLOR)
    return cv2.imwrite(filename, frame)
        