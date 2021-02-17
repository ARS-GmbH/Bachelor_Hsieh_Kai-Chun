"""
Copyright (c) 2020 ARS Computer & Consulting GmbH

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
"""

from sklearn import svm
from sklearn import preprocessing
from scipy.stats import entropy
from . import interface

import cv2
import numpy as np
import time
import os
import json
import pickle

MODEL_DIRECTORY = "data/localfoameliminationdetector"
MODEL_ID_PREFIX = "foameliminationdetector-1.0"


def reflector():
    return LocalFoamEliminationDetector


class LocalFoamEliminationDetector(interface.SolutionManager):

    def __init__(self, datatableName, serverAPI):
        self._datatableName = datatableName
        self._serverAPI = serverAPI

        import os
        if not os.path.exists(MODEL_DIRECTORY):
            os.makedirs(MODEL_DIRECTORY)

    # getters of basic metadata
    @staticmethod
    def getManufacturer():
        return "edu.hm.hsieh"

    @staticmethod
    def getAuthor():
        return "hsieh"

    @staticmethod
    def getName():
        return "localfoameliminationdetector"

    @staticmethod
    def getVersion():
        return "1.0"

    @staticmethod
    def getDescription():
        return "This is model extracts different features from input photos and train/classify using a SVM."

    @staticmethod
    def getPriceDescription():
        return "Resource this model needs is only CPU resouces of the local computer. However user should also be aware of costs of downloading/caching input photos."

    # service handlers

    def createModel(self, database, id):
        # reserve neccessory resources from the new model and fill the record into database

        session = database.cursor()
        session.execute("INSERT INTO " +
                        self._datatableName +
                        " (id, remote_id) VALUES (%s, %s)", (id, MODEL_ID_PREFIX +
                                                             "-" +
                                                             str(int(time.time_ns())) +
                                                             ".model"))
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
            onMessage("Training starting...")
            modelSaveName, trainingData, _ = result

            onMessage("Downloading/Caching photos...")

            start = time.time()

            images = []
            dataClasses = []
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
                    images.append(image)
                    dataClasses.append(trainingData[photoID])

                    onMessage(visualizeImageDownload())

            end = time.time()
            onMessage("Caching image done: " + str(end - start))

            if imageOK < 2:
                onMessage(
                    "Model training aborted.  Number of successfully downloaded training data is not enough.")
                onFinished(False)
                return

            onMessage("Training model with " + str(imageOK) + " photos...")

            # get photo features
            features, scaler = self._getImageFeatures(images)

            newModel = svm.LinearSVC()

            try:
                train(newModel, features, dataClasses)

            except Exception as err:
                onMessage("Failed to train model, debug message: " + str(err))
                onFinished(False)
                return

            onMessage("Training done saving model...")
            try:
                with open("./" + MODEL_DIRECTORY + "/" + modelSaveName, 'wb') as modelFile:
                    pickle.dump(newModel, modelFile, protocol=pickle.HIGHEST_PROTOCOL)
                with open("./" + MODEL_DIRECTORY + "/" + "scaler-" + modelSaveName, 'wb') as scalerFile:
                    pickle.dump(scaler, scalerFile, protocol=pickle.HIGHEST_PROTOCOL)

            except Exception as err:
                onMessage("Failed to save the trained model, debug message: " + str(err))
                onFinished(False)
                return

            print("Model saved as " + modelSaveName)

            onMessage("Model saved.")
            onFinished(True)
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
            resultMap = {}

            photoIDs = []
            opencvImages = []

            if len(inputDataIDs) > 0:
                modelFileName = result[0]

                # load photos
                for photoID in inputDataIDs:

                    image, _, err = self._serverAPI.getResource(database, photoID)
                    if err is None:
                        photoIDs.append(photoID)
                        opencvImages.append(image)

                predictResult = self._predict(modelFileName, opencvImages)

                if predictResult is None:
                    onFinished({"ISOK": False})
                    return

                for index in range(len(photoIDs)):
                    resultMap[photoIDs[index]] = {"CLASS": str(predictResult[index]), "SCORE": 1.0}

            onFinished({"ISOK": True, "RESULT": resultMap})
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
            modelFileName = result[0]

            resultMap = {}
            predictResult = []

            if len(inputOpenCVImages) > 0:
                predictResult = self._predict(modelFileName, inputOpenCVImages)

                if predictResult is None:
                    onFinished({"ISOK": False})
                    return

                for index in range(len(predictResult)):
                    resultMap[imageNames[index]] = {
                        "CLASS": str(predictResult[index]), "SCORE": 1.0}

            onFinished({"ISOK": True, "RESULT": resultMap})
        else:
            print("ERROR (", self._datatableName, ") Model", modelID,
                  "failed to predict, model record not found by plugin.")
            onFinished({"ISOK": False})

    def _getImageFeatures(self, opencvPhotos, scaler=None):
        features = getFeatures(opencvPhotos)
        features, scaler = normalizeDataset(features, scaler)

        return features, scaler

    def _predict(self, modelFileName, opecvPhotos):

        predictResult = []

        assert (len(opecvPhotos) > 0)

        # load model and scalers
        try:
            with open("./" + MODEL_DIRECTORY + "/" + modelFileName, "rb") as modelStream:
                model = pickle.load(modelStream)
            with open("./" + MODEL_DIRECTORY + "/" + "scaler-" + modelFileName, "rb") as scalerStream:
                scaler = pickle.load(scalerStream)
        except Exception as err:
            print("ERROR (", self._datatableName, ") Model", modelFileName,
                  "failed to be loaded, debug message: " + str(err))
            return None

        # get photo features
        features, _ = self._getImageFeatures(opecvPhotos, scaler)
        predictResult = model.predict(features)

        return predictResult


### The Solution this model using ###


def getOpenCVImageColorMSE(image):
    # calculate color difference factor D:
    # source: 基于SVM的图像分类算法与实现

    averageColor = np.average(image)
    averageFilter = np.full((len(image), len(image[0]), 3), averageColor)

    return np.sqrt(((image - averageFilter) ** 2).sum(axis=2)).mean()


def getFeatures(images):
    dataset = []

    for image in images:
        features = []

        # calculate feature 1: MSE of colors of a image
        features.append(getOpenCVImageColorMSE(image))

        # calculate feature 2: entropy from edges of a image

        # image prepocessing
        grayImage = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(grayImage, (3, 3), 0)

        # graphic processing
        sobelX = cv2.Sobel(blurred, -1, 1, 0, ksize=5)
        sobelY = cv2.Sobel(blurred, -1, 0, 1, ksize=5)
        sobelXY = cv2.addWeighted(sobelX, 0.5, sobelY, 0.5, 0)
        #sobelYnp.arctan2(np.absolute(sobelX), np.absolute(sobelY))

        # compute entropy
        features.append(entropy(sobelXY.flatten()))

        dataset.append(features)

    return dataset


def normalizeDataset(dataset, scaler=None):

    if scaler is None:
        #scaler = preprocessing.RobustScaler()
        #scaler = preprocessing.StandardScaler()
        scaler = preprocessing.MinMaxScaler()
        scaler.fit(dataset)

    return scaler.transform(dataset), scaler


def train(model, dataset, dataTags):
    model.fit(dataset, dataTags)  # training the svc model
