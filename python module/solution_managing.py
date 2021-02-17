"""
Copyright (c) 2020 ARS Computer & Consulting GmbH

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
"""

import requests
import os
import pandas
from cv2 import cv2 as cv
import numpy as np
import time, datetime
import subprocess, io
import notification, utils

NUMBER_DETECTION = 1
SCORE = 2
NUMBER_DETECTION_AND_SCORE = 3
NUMBER_DETECTION_OR_SCORE = 4

PREDICTION_VIEW_TABLE = 1
PREDICTION_VIEW_PHOTO = 2

class SolutionManager:
    """
    Client library for managing solutions and models.
    """

    def __init__(self, address, port):
        """
        Constructor.

        Args:
            address (str): IP or URL of the server.
            port (str): Port of the server.

        Returns:
            No Returns.
        """

        self._address = address
        self._port = port

    def getPluginList(self, table_view = False):
        """
        Get the list of solution managment plugins installed on the server.

        Args:
            table_view (bool): Whether render response with table-view.

        Returns:
            response (obj): Json by default; pandas Dataframe by table-view mode. Contains columns: id, name, manufacturer, version, description and price description.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        res = requests.get("http://" + self._address + ":" + str(self._port) + "/solution_plugins")
        if res.status_code == 200:

            if table_view:
                tableHeaders = ["id", "name", "manufacturer", "version", "description", "price description"]
                data = [] 

                for plugin in res.json():
                    data.append([plugin["id"], plugin["name"], plugin["manufacturer"], plugin["version"], plugin["description"], plugin["price_description"]])
                
                return pandas.DataFrame(data, columns = tableHeaders)
            else:
                return res.json()

        else:
            raise RuntimeError("Unknown error code: " + str(res.status_code))

    def createNewModel(self, solutionID, modelNickName, modelDescription):
        """
        Create a new model with specified solution.

        Args:
            solutionID (str): ID of the solution plugin.
            modelNickName (str): Nickname of the new model. Must be server-wide unique, otherwise, 400 Bad Request will be produced.
            modelDescirption (str): Random description for the new model.

        Returns:
            newModel (Model): An model object as handle.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        payload = {}
        if modelNickName:
            payload["nickname"] = modelNickName

        if modelDescription:
            payload["description"] = modelDescription

        res = requests.post("http://" + self._address + ":" + str(self._port) + "/create_model", 
                            params={"solutionID": solutionID}, 
                            json=payload)

        if res.status_code == 200:
            return Model(int(res.text), self._address, self._port)
        elif res.status_code == 410:
            raise RuntimeError("Failed to create a new model: " + res.text)
        else:
            raise RuntimeError("Unknown server error: " + str(res.status_code))

    def getModelList(self, table_view = False):
        """
        Get the list of models created on the server.

        Args:
            table_view (bool): Whether render response with table-view.

        Returns:
            response (obj): Json by default; pandas Dataframe by table-view mode. Contains colums: ID, CREATED-BY, CREATED-AT, PLUGIN-ID, MIME, EXTRA_INFO.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        res = requests.get("http://" + self._address + ":" + str(self._port) + "/models")
        if res.status_code == 200:

            if table_view:
                tableHeaders = ["id", "nickname", "created at", "created by", "plugin ID", "state", "description"]
                data = [] 

                for plugin in res.json():
                    data.append([plugin["id"], plugin["nickname"], plugin["created_at"], plugin["create_by"], plugin["plugin_id"], plugin["state"], plugin["description"]])
                
                return pandas.DataFrame(data, columns = tableHeaders)
            else:
                return res.json()

        else:
            raise RuntimeError("Unknown error code: " + str(res.status_code))

    def modelFactory(self, modelID):
        """
        A factory method to create an instance model.

        Args:
            modelID (int): ID of the model.

        Returns:
            response (obj): Json by default; pandas Dataframe by table-view mode.
            
        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        return Model(modelID, self._address, self._port)

class Model:
    """
    Model instance and its APIs.
    """

    def __init__(self, modelID, serverAddress, serverPort):
        """
        Constructor

        Args:
            modelID (int): ID of the model.
            serverAddress (str): IP or URL of the server.
            serverPort (str): Port of the server.
        """

        self._modelID = modelID
        self._serverAddress = serverAddress
        self._serverPort = serverPort

    def getID(self):
        """
        Get the id of this model.

        Returns:
            modelID (int): ID of this model.
        """

        return self._modelID

    def feed_train_data(self, resourceList, dataClass):
        """
        Feed training data into model.

        Args:
            resourceList (obj): A resource_managing.ResourceList resource list.
            dataClass (str): Class-tag that resources in the resourceList will be labeled with.

        Returns:
            result (str): "OK" if ok.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """
        resourceIDs = resourceList.getIDs()
        
        # tag data
        dataset = {}
        for resourceID in resourceIDs:
            dataset[resourceID] = dataClass
        
        res = requests.post("http://" + self._serverAddress + ":" + str(self._serverPort) + "/feed_train_data", params={"modelID": self._modelID}, json=dataset)

        if res.status_code == 200 and res.text == "OK":
            return "OK"
        elif res.status_code == 400 or res.status_code == 404 or res.status_code == 410:
            raise RuntimeError(res.text)
        else:
            raise RuntimeError("Unknown server error: " + res.text)

    def train(self, parameter = None):
        """
        Train this model with dataset fed earlier.

        Args:
            parameter (obj): A dict containing parameters for customizing training.

        Returns:
            training_logs (str): Live logging of the training process.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        session = requests.Session()
        with session.post("http://" + self._serverAddress + ":" + str(self._serverPort) + "/train_model", params={"modelID": self._modelID}, json=parameter, stream=True) as res:
            print("INFO Server answered training model result=" + str(res.status_code))
            if res.status_code == 200:
                print("INFO Training starting:")

                for line in res.iter_lines():
                    if line:
                        print(line.decode())
            else:
                raise RuntimeError("Server rejected the training request, err: " + res.text)
    

    def predictWithResourceList(self, resourceList, view=None):
        """
        Make predictions on the resources listed.

        Args:
            resourceList (obj): A resource_managing.ResourceList resource list.
            view (int): Type of renderer appling on prediction-responses, supporting PREDICTION_VIEW_TABLE and REDICTION_VIEW_PHOTO.

        Returns:
            result (obj): Parsed Json object if no view-type is set. pandas.DataFrame if table-view set. Nothing returned by photo-view but will displays rendered photos automatically.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        res = requests.post("http://" + self._serverAddress + ":" + str(self._serverPort) + "/predict_w_list", params={"modelID": self._modelID}, json=resourceList.getIDs())
        
        if res.status_code == 200:
            res = res.json()
            
            if res["ISOK"]:
                if view == PREDICTION_VIEW_TABLE:
                    return _toTableView(res["RESULT"])
                elif view == PREDICTION_VIEW_PHOTO:
                    return _toPhotoView(res["RESULT"], self._serverAddress, self._serverPort)
                else:
                    return res["RESULT"]
            else:
                raise RuntimeError("Predict failed.")
        else:
            raise RuntimeError("ERROR Unknown server error with code: " + str(res.status_code))
    
    def predict(self, resourceFileName, view=None):
        """
        Upload and make prediction on a file.

        Args:
            resourceFileName (str): Filename of the resource to be predicted.
            view (int): Type of renderer appling on prediction-responses, supporting PREDICTION_VIEW_TABLE and REDICTION_VIEW_PHOTO.

        Returns:
            result (obj): Parsed Json object if no view-type is set. pandas.DataFrame if table-view set. Nothing returned by photo-view but will displays rendered photos automatically.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        return self.predictWithResources([resourceFileName], view)

    def predictWithResources(self, resourceFilenameList, view=None):
        """
        Upload files and make prediction on them.

        Args:
            resourceFilenameList (List<str>): List of filenames that will be uploaded.
            view (int): Type of renderer appling on prediction-responses, supporting PREDICTION_VIEW_TABLE and REDICTION_VIEW_PHOTO.

        Returns:
            result (obj): Parsed Json object if no view-type is set. pandas.DataFrame if table-view set. Nothing returned by photo-view but will displays rendered photos automatically.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        files = []

        modelName = self.getID()

        for resourceFile in resourceFilenameList:
            file = open(resourceFile, "rb")
            files.append(("file[]", (resourceFile, file)))

        res = requests.post("http://" + self._serverAddress + ":" + str(self._serverPort) + "/predict", files=files, data={"modelID": modelName})
        
        if res.status_code == 200:
            res = res.json()
            
            if res["ISOK"]:
                if view == PREDICTION_VIEW_TABLE:
                    return _toTableView(res["RESULT"])
                elif view == PREDICTION_VIEW_PHOTO:
                    return _toPhotoView(res["RESULT"], self._serverAddress, self._serverPort)
                else:
                    return res["RESULT"]
            else:
                raise RuntimeError("Predict failed.")
        else:
            raise RuntimeError("ERROR Unknown server error with code: " + str(res.status_code))
    
    def streamPredict(self, ffmpegPath, captureInterval, experimentLength, cameraName, targetPredictionClass, notificator, 
                      messageType=notification.MESSAGE_TYPE_TEXT,
                      triggerMode=NUMBER_DETECTION, 
                      classDetectedThreshold=1,
                      scoreThreshold=1.0):
        """
        Make autonomous real-time classification with cameras. 

        Args:
            ffmpegPath (str): Path of the ffmpeg execuable.
            captureInterval (int): Interval of taking a photo.
            experimentLength (int): Interval of the whole experiment.
            cameraName (int): Name of the camera connecting to.
            targetPredictionClass (str): The target class this script to be aware of.
            notificator (Notifcation): The notificator to send message with.
            messageType (int): Type of the notificator, e.g. notification.MESSAGE_TYPE_TEXT.
            triggerMode (int): Mode of trigger producing notifications.
            classDetectedThreshold (int): Threshold of trigger on number of detections against target-class.
            classDetectedThreshold (float): Threshold of trigger on confidience of target-class.
        """
        
        cameraName = cameraName.strip()

        assert len(cameraName) > 0
        triggerCounter = 0
            
        for _ in range(experimentLength // captureInterval):
            tempFileName = "temp-" + str(time.time_ns()) + ".png"

            result, err = _ffmpegCaptureAFrame(ffmpegPath, cameraName, tempFileName)
                
            if result:
                print("DEBUG A Photo was succesfully taken at", datetime.datetime.now())
                predictResult = self.predictWithResources([tempFileName])
                if predictResult:
                    if len(predictResult.keys()) != 1:
                        print("ERROR Invalid predicted entry numbers:", len(predictResult.keys()))
                    else:
                        sortedToClass = predictResult[list(predictResult.keys())[0]]["CLASS"]
                        scoreRaw = predictResult[list(predictResult.keys())[0]]["SCORE"]
                        tag, score = _toImageTag(sortedToClass, scoreRaw)

                        trigger  = False

                        if triggerMode == SCORE:
                            if scoreRaw >= scoreThreshold:
                                trigger = True

                        elif triggerMode == NUMBER_DETECTION_AND_SCORE:
                            if scoreRaw >= scoreThreshold and sortedToClass == str(targetPredictionClass):
                                triggerCounter += 1
                            else:
                                triggerCounter = 0

                            if triggerCounter >= classDetectedThreshold:
                                trigger = True

                        elif triggerMode == NUMBER_DETECTION_OR_SCORE:

                            if sortedToClass == str(targetPredictionClass):
                                triggerCounter += 1
                            else:
                                triggerCounter == 0

                            if triggerCounter >= classDetectedThreshold or scoreRaw >= scoreThreshold:
                                trigger = True

                        else:
                            # default: Number of detection mode
                            if sortedToClass == str(targetPredictionClass):
                                triggerCounter += 1
                            else:
                                triggerCounter == 0

                            if triggerCounter >= classDetectedThreshold:
                                trigger = True

                        if trigger:
                            if messageType == notification.MESSAGE_TYPE_IMAGE:
                                try:
                                    with open(tempFileName, "rb") as imageFile:
                                        # load image
                                        opencvImage = cv.imdecode(np.fromstring(imageFile.read(), np.uint8), cv.IMREAD_COLOR)
                                        _tagPhoto(opencvImage, "Class: " + tag + "(" + score + ")")

                                        _, buffer = cv.imencode(".png", opencvImage)
                                        notificator.sendMessage(notification.MESSAGE_TYPE_IMAGE, io.BytesIO(buffer))
                                except Exception as err:
                                    raise RuntimeError("Failed to read saved temp image file: " +  tempFileName + str(err))       
                            else:
                                notificator.sendMessage(notification.MESSAGE_TYPE_TEXT, "Target class '" + tag + "'(" + score + ") detected!")
            
                else:
                    print("ERROR Stream predict failed.")

                
                # all done, remove the temp image file
                os.remove(tempFileName)
                
            else:
                print("DEBUG Photo taken was failed. Debug messages:")
                
                output = err.readline()

                while len(output) > 0:
                    trimedOutput = output.decode().strip()
                    print(trimedOutput)
                    
                    output = err.readline()
            
            time.sleep(captureInterval)


# Private static functions

def _toImageTag(tag, score):
    return str(tag), str(int(score * 10000) / 100 ) + "%"

def _toTableView(predictionResult):
    tableHeaders = ["id", "class", "score"]
    data = [] 

    for imageID in predictionResult.keys():
        tag, score = _toImageTag(predictionResult[imageID]["CLASS"], predictionResult[imageID]["SCORE"])
        data.append([imageID, tag, score])
            
    return pandas.DataFrame(data, columns = tableHeaders)

def _tagPhoto(opencvImage, tag):
    font = cv.FONT_HERSHEY_DUPLEX

    textsize = cv.getTextSize(tag, font, 1, 2)[0]

    cv.rectangle(opencvImage, (10 - 10, 40 + 10), (10 + textsize[0] + 10, 40 + 10 - textsize[1] - 20), (0, 0, 0), -1)
    cv.putText(opencvImage, tag, (10, 40), font, 1, (0, 255, 255), 2, cv.LINE_AA)

def _toPhotoView(predictionResult, severAddress, serverPort):

    for photoID in predictionResult:
        isID = True

        try:
            int(photoID)
        except:
            isID = False

        image = None
        
        if isID:
            # download from server
            res = requests.get("http://" + severAddress + ":" + str(serverPort) + "/get_resource/" + photoID, stream=True)
            if res.status_code == 200:
                image = np.asarray(bytearray(res.raw.read()), dtype="uint8")
                image = cv.imdecode(image, cv.IMREAD_COLOR)

            else:
                raise RuntimeError("Cache image " + str(photoID) + " failed with code: " + str(res.status_code))
        
        else:
            image = cv.imread(photoID)

        if image is not None:
            tag, score = _toImageTag(predictionResult[photoID]["CLASS"], predictionResult[photoID]["SCORE"])
            label = "Class: " + tag + "(" + score + ")"
            _tagPhoto(image, label)

            utils.showOpenCVImage(image, photoID)

def _ffmpegCaptureAFrame(ffmpegPath, cameraName, outputFilename):
    captureFrame = subprocess.run(
        [ffmpegPath, "-n", "-hide_banner", "-f", "dshow", "-i", 
         "video=" + cameraName, "-vframes", "1", outputFilename],
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE)

    if captureFrame.returncode == 0:
        return True, None
    else:
        return False, io.BytesIO(captureFrame.stderr)