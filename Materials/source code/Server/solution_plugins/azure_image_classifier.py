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
import time
import os
import json
import pickle

from azure.cognitiveservices.vision.customvision.training import CustomVisionTrainingClient
from azure.cognitiveservices.vision.customvision.training.models import ImageFileCreateEntry
from azure.cognitiveservices.vision.customvision.prediction import CustomVisionPredictionClient

MODEL_ID_PREFIX = "azureimageclassifier-1.0"


def reflector():
    return AzureCustomVision


class AzureCustomVision(interface.SolutionManager):

    def __init__(self, datatableName, serverAPI):
        self._datatableName = datatableName
        self._serverAPI = serverAPI
        self._endPoint = "https://westeurope.api.cognitive.microsoft.com/"
        self._trainingKey = "b50e09c56a454914b05c7434139834f0"
        self._predictionKey = "b50e09c56a454914b05c7434139834f0"
        self._resourceID = "/subscriptions/8c890f11-4343-44c3-8a8e-3fbfe6b3fa63/resourceGroups/HM_Bachelorarbeit/providers/Microsoft.CognitiveServices/accounts/HM_Bachelorarbeit"

    # getters of basic metadata
    @staticmethod
    def getManufacturer():
        return "edu.hm.hsieh"

    @staticmethod
    def getAuthor():
        return "hsieh"

    @staticmethod
    def getName():
        return "azureimageclassifier"

    @staticmethod
    def getVersion():
        return "1.0"

    @staticmethod
    def getDescription():
        return "This model uses Microsoft Azure Custom Vision to provide better image classification experience."

    @staticmethod
    def getPriceDescription():
        return "Pricing see: https://azure.microsoft.com/en-us/pricing/"

    # service handlers
    def createModel(self, database, id):

        trainer = CustomVisionTrainingClient(self._trainingKey, endpoint=self._endPoint)
        project = trainer.create_project(MODEL_ID_PREFIX + "-" + str(time.time_ns()))

        # reserve neccessory resources from the new model and fill the record into database
        session = database.cursor()
        session.execute("INSERT INTO " + self._datatableName +
                        " (id, remote_id) VALUES (%s, %s)", (id, project.id))
        database.commit()

        return True

    def feedTrainData(self, database, id, newTrainData):
        # get model record from database

        session = database.cursor()
        session.execute("SELECT remote_id, training_data, extra_info FROM " +
                        self._datatableName + " WHERE id = %s", (id,))
        result = session.fetchone()
        session.close()

        if result is None:
            print("INFO (", self._datatableName, ") Model", id,
                  "can no longer be found from the plugin database.")
            return False, "model can not be found from plugin database"

        _, trainingData, _ = result
        if trainingData is None:
            trainingData = {}

        trainingData = {**trainingData, **newTrainData}

        # update record
        session = database.cursor()
        session.execute(
            "UPDATE " +
            self._datatableName +
            " SET training_data=%s WHERE id=%s;",
            (json.dumps(trainingData),
             id))
        database.commit()

        return True, None

    def trainModel(self, database, modelID, parameters, onMessage, onFinished):
        onMessage("Trainer fetching model settings.")
        session = database.cursor()
        session.execute("SELECT remote_id, training_data, extra_info FROM " +
                        self._datatableName + " WHERE id = %s", (modelID,))
        result = session.fetchone()
        session.close()

        if result:
            projectID, trainingData, _ = result

            onMessage("Training starting...")

            onMessage("Retrieving model...")
            trainer = CustomVisionTrainingClient(self._trainingKey, endpoint=self._endPoint)
            project = trainer.get_project(projectID)

            onMessage("Downloading/Caching and Analyzing training data...")

            imageList = []
            dataClassList = {}

            try:
                start = time.time()
                # retrieve information of created tags
                createdTags = trainer.get_tags(projectID)
                for tag in createdTags:
                    dataClassList[tag.name] = tag

                imageOK = 0
                imageFailed = 0
                imageTotal = len(trainingData)

                def visualizeImageDownload():
                    return "(" + str(imageOK) + "/" + str(imageFailed) + "/" + str(imageTotal) + ")"

                for photoID in trainingData:
                    image, _, err = self._serverAPI.getResource(database, photoID)

                    if err:
                        imageFailed += 1
                        onMessage(
                            "Failed to download image " +
                            str(photoID) +
                            ". Error: " +
                            err +
                            " " +
                            visualizeImageDownload())
                    else:
                        imageOK += 1

                        classOfData = str(trainingData[photoID])

                        # create tag if not exists
                        if classOfData not in dataClassList:
                            dataClassList[classOfData] = trainer.create_tag(project.id, classOfData)

                        isOK, encodedImage = cv2.imencode('.png', image)
                        imageList.append(
                            ImageFileCreateEntry(
                                name=str(photoID) + ".png",
                                contents=encodedImage,
                                tag_ids=[
                                    dataClassList[classOfData].id]))

                        onMessage(visualizeImageDownload())
                end = time.time()
                onMessage("Image caching done. Used: " + str(end - start))

                start = time.time()
                for i in range(0, len(imageList), 64):
                    batch = imageList[i:i + 64]
                    upload_result = trainer.create_images_from_files(project.id, images=batch)

                    if not upload_result.is_batch_successful:
                        onMessage("Image batch upload failed.")

                        for image in upload_result.images:
                            onMessage("Image status: ", image.status)

                        onFinished(False)
                        return
                end = time.time()
                onMessage("Image upload done. Used: " + str(end - start))

                onMessage("Training model with " + str(imageOK) + " photos...")

                iteration = trainer.train_project(project.id)
                while (iteration.status != "Completed"):
                    iteration = trainer.get_iteration(project.id, iteration.id)
                    onMessage("Training status: " + iteration.status)
                    time.sleep(3)

                # The iteration is now trained. Publish it to the project endpoint
                trainer.publish_iteration(project.id, iteration.id, projectID, self._resourceID)
                onMessage("Training done.")
                onFinished(True)

            except Exception as err:
                onMessage("Failed to train.")
                onMessage("Error Message: " + str(err))
                onFinished(False)
        else:
            onMessage("The trainer can't recognize the given model any more.")
            onFinished(False)

    def predictWithID(self, database, modelID, inputDataIDs, onFinished):

        # load model record
        session = database.cursor()
        session.execute(
            "SELECT remote_id FROM " +
            self._datatableName +
            " WHERE id = %s",
            (modelID,
             ))
        result = session.fetchone()
        session.close()

        if result:
            projectID = result[0]

            predictOK = True
            resultMap = {}

            if len(inputDataIDs) > 0:
                try:
                    # Now there is a trained endpoint that can be used to make a prediction
                    trainer = CustomVisionTrainingClient(self._trainingKey, endpoint=self._endPoint)
                    predictor = CustomVisionPredictionClient(
                        self._predictionKey, endpoint=self._endPoint)
                    project = trainer.get_project(projectID)

                    # load photos
                    for photoID in inputDataIDs:

                        image, _, err = self._serverAPI.getResource(database, photoID)
                        if err is None:
                            isOK, encodedImage = cv2.imencode('.png', image)
                            predictResponse = predictor.classify_image(
                                project.id, projectID, encodedImage)
                            predictResult = predictResponse.predictions
                            if len(predictResult) > 0:
                                resultMap[photoID] = {
                                    "CLASS": predictResult[0].tag_name,
                                    "SCORE": predictResult[0].probability}

                except Exception as err:
                    predictOK = False
                    resultMap = {}
                    print("ERROR (", self._datatableName, ") Model",
                          modelID, "failed to predict: " + str(err))

                    #raise err

            onFinished({"ISOK": predictOK, "RESULT": resultMap})

        else:
            print("ERROR (", self._datatableName, ") Model", modelID,
                  "failed to predict, model record not found by plugin.")
            onFinished({"ISOK": False})

    def predictWithData(self, database, modelID, imageNames, inputOpenCVImages, onFinished):
        # load model record
        session = database.cursor()
        session.execute(
            "SELECT remote_id FROM " +
            self._datatableName +
            " WHERE id = %s",
            (modelID,
             ))
        result = session.fetchone()
        session.close()

        if result:
            projectID = result[0]

            predictOK = True
            resultMap = {}

            if len(inputOpenCVImages) > 0:
                try:
                    # Now there is a trained endpoint that can be used to make a prediction
                    trainer = CustomVisionTrainingClient(self._trainingKey, endpoint=self._endPoint)
                    predictor = CustomVisionPredictionClient(
                        self._predictionKey, endpoint=self._endPoint)
                    project = trainer.get_project(projectID)

                    # load photos
                    for index in range(len(inputOpenCVImages)):
                        photoID = imageNames[index]
                        image = inputOpenCVImages[index]

                        isOK, encodedImage = cv2.imencode('.png', image)
                        predictResponse = predictor.classify_image(
                            project.id, projectID, encodedImage)
                        predictResult = predictResponse.predictions
                        if len(predictResult) > 0:
                            resultMap[photoID] = {
                                "CLASS": predictResult[0].tag_name,
                                "SCORE": predictResult[0].probability}

                except Exception as err:
                    predictOK = False
                    resultMap = {}
                    print("ERROR (", self._datatableName, ") Model",
                          modelID, "failed to predict: " + str(err))

                    #raise err

            onFinished({"ISOK": predictOK, "RESULT": resultMap})
        else:
            print("ERROR (", self._datatableName, ") Model", modelID,
                  "failed to predict, model record not found by plugin.")
            onFinished({"ISOK": False})
