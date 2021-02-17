"""
Copyright (c) 2020 ARS Computer & Consulting GmbH

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
"""

# imports
import os
import importlib
import utils
import queue
import threading
from flask import jsonify, request, Response
from resource_loader import ALLOWED_EXTENSIONS, _getMimeFromExtension
import json
from cv2 import cv2 as cv
import numpy as np

# static parameters
MODEL_TAG_MODEL = "model_manager"

SOLUTION_PLUGINS_PATH = "solution_plugins"

STATE_MODEL_CREATED = 0
STATE_DATA_FEEDING = 10
STATE_TRAINING = 20
STATE_MODEL_USABLE = 30

stateID2State = {
    0: "STATE_MODEL_CREATED",
    10: "STATE_DATA_FEEDING",
    20: "STATE_TRAINING",
    30: "STATE_MODEL_USABLE",
}


solutionPlugins = {}


def initialize(database, app, serverAPI):
    # initialize model database
    session = database.cursor()
    session.execute("CREATE TABLE IF NOT EXISTS models\
                    (\
                        id integer NOT NULL,\
                        nickname text,\
                        created_at timestamp without time zone NOT NULL,\
                        create_by text NOT NULL,\
                        plugin_id text NOT NULL,\
                        state integer NOT NULL,\
                        description text,\
                        PRIMARY KEY (id)\
                    )\
                    WITH (\
                        OIDS = FALSE\
                    );")
    database.commit()

    # initialize model-resource index
    session = database.cursor()
    session.execute("INSERT INTO resource_indexes (module_id, next_index)\
                    SELECT '" + MODEL_TAG_MODEL + "', 0\
                    WHERE NOT EXISTS (SELECT 1 FROM resource_indexes WHERE module_id = '" + MODEL_TAG_MODEL + "');")
    database.commit()

    # load solution managers
    for plugin in os.listdir("./" + SOLUTION_PLUGINS_PATH):
        pluginFilename = plugin

        if pluginFilename.endswith(".py") and not pluginFilename.startswith(
                "interface") and not pluginFilename.startswith("__init__"):
            pluginModule = importlib.import_module(
                SOLUTION_PLUGINS_PATH + "." + pluginFilename[:-3])

            try:
                pluginClass = pluginModule.reflector()
            except BaseException:
                print("ERROR Solution plugin", pluginFilename,
                      "was refused to load: ERR_NO_REFLECTOR_METHOD")
                continue

            try:
                instanceID = utils.getPluginID(pluginClass)
            except BaseException:
                print("ERROR Solution plugin", pluginFilename,
                      "was refused to load: ERR_METADATA_INVALID")
                continue

            databaseID = utils.getPluginDataTableID(instanceID)

            try:
                # create a datatable for this plugin if it not exists
                session = database.cursor()
                session.execute("CREATE TABLE IF NOT EXISTS " + databaseID + "\
                                (\
                                    id integer NOT NULL,\
                                    remote_id text NOT NULL,\
                                    training_data json,\
                                    extra_info json,\
                                    PRIMARY KEY (id)\
                                )\
                                WITH (\
                                    OIDS = FALSE\
                                );")
                database.commit()

            except BaseException:
                print("ERROR Solution plugin", pluginFilename,
                      "was refused to load: ERR_DATATABLE_CREATE_FAILED")
                continue

            solutionPlugins[instanceID] = {
                "instance": pluginClass(
                    databaseID,
                    serverAPI),
                "class": pluginClass}

    print("INFO", len(solutionPlugins), "solution plugins loaded.")

    @app.route('/solution_plugins', methods=['GET'])
    def solutionPluginInfoProvider():
        loaders = []

        for loader in solutionPlugins:
            pluginClass = solutionPlugins[loader]["class"]

            loaders.append({
                "id": utils.getPluginID(pluginClass),
                "manufacturer": pluginClass.getManufacturer(),
                "author": pluginClass.getAuthor(),
                "name": pluginClass.getName(),
                "version": pluginClass.getVersion(),
                "description": pluginClass.getDescription(),
                "price_description": pluginClass.getPriceDescription(),
            })

        return jsonify(loaders)

    @app.route('/create_model', methods=['POST'])
    def modelCreater():
        solutionID = request.args.get('solutionID')

        if solutionID is None:
            return "Solution ID was not specified.", 400

        elif solutionID not in solutionPlugins:
            return "Solution with specified ID is not found.", 404
        else:
            modelInfo = request.get_json()
            if "nickname" in modelInfo:
                nickName = modelInfo['nickname']
                # check is nickname unique
                session = database.cursor()
                session.execute("SELECT 1 from models WHERE nickname=%s;", (nickName,))
                numberOfNickname = session.rowcount
                session.close()

                if numberOfNickname > 0:
                    return "Nickname is already used, use another.", 400

            else:
                nickName = None

            if "description" in modelInfo:
                description = modelInfo['description']
            else:
                description = None

            newID = utils.reserveNewID(database, MODEL_TAG_MODEL)
            result = solutionPlugins[solutionID]["instance"].createModel(database, newID)

            # write the record of the created model into database
            session = database.cursor()
            session.execute(
                "INSERT INTO models (id, nickname, created_at, create_by, plugin_id, state, description) VALUES (%s, %s, NOW(), %s, %s, %s, %s);",
                (newID,
                 nickName,
                 "webuser0",
                 solutionID,
                 STATE_MODEL_CREATED,
                 description))

            database.commit()

            if result:
                return str(newID), 200
            else:
                return "Failed to create a new model.", 410

    @app.route('/models', methods=['GET'])
    def modelInfoProvider():
        session = database.cursor()
        session.execute(
            "SELECT id, nickname, created_at, create_by, plugin_id, state, description FROM models ORDER BY id DESC;")
        results = session.fetchall()
        session.close()

        models = []

        for result in results:
            id, nickname, created_at, create_by, plugin_id, state, description = result

            models.append({
                "id": id,
                "nickname": nickname,
                "created_at": created_at,
                "create_by": create_by,
                "plugin_id": plugin_id,
                "state": stateID2State[state],
                "description": description,
            })

        return jsonify(models)

    @app.route('/feed_train_data', methods=['POST'])
    def feedModelTrainData():
        modelName = request.args.get('modelID')  # can be number: modelID, or model nickname

        # parse body: training data
        if not request.is_json:
            return "Bad training data.", 400

        trainingData = request.get_json()
        if trainingData is None:
            return "Bad training data format.", 400

        # get modelID from given id or nickname
        session = database.cursor()
        try:
            queryModelID = int(modelName)
            queryModelNickName = None
        except BaseException:
            queryModelID = -1
            queryModelNickName = modelName

        session.execute(
            "SELECT id, plugin_id, state FROM models WHERE id=%s OR nickname=%s;",
            (queryModelID,
             queryModelNickName))
        result = session.fetchone()
        session.close()

        if result is None:
            return "No model with given modelID was found.", 404

        modelID, pluginID, modelState = result

        if modelState > STATE_DATA_FEEDING:
            return "Model with state " + \
                stateID2State[modelState] + " is no longer allowed to give training data.", 400

        result, err = solutionPlugins[pluginID]["instance"].feedTrainData(
            database, modelID, trainingData)
        if result:
            # update model state
            session = database.cursor()
            session.execute("UPDATE models SET state=%s WHERE id=%s;",
                            (STATE_DATA_FEEDING, modelID))
            database.commit()

            return "OK"

        else:
            return err, 410

    @app.route('/train_model', methods=['GET', 'POST'])
    def modelTrainer():
        modelName = request.args.get('modelID')  # can be number: modelID, or model nickname

        trainingParameter = None

        if request.is_json:
            trainingParameter = request.get_json()
            if trainingParameter is None or not isinstance(trainingParameter, dict):
                return "Bad training parameter format.", 400

        # get modelID from given id or nickname
        session = database.cursor()
        try:
            queryModelID = int(modelName)
            queryModelNickName = None
        except BaseException:
            queryModelID = -1
            queryModelNickName = modelName

        session.execute(
            "SELECT id, plugin_id, state FROM models WHERE id=%s OR nickname=%s;",
            (queryModelID,
             queryModelNickName))
        result = session.fetchone()
        session.close()

        if result is None:
            return "No model with given modelID was found.", 404

        modelID, pluginID, modelState = result

        if modelState != STATE_DATA_FEEDING:
            return "Can't train model with state: " + stateID2State[modelState], 400

        # update model state to training
        session = database.cursor()
        session.execute("UPDATE models SET state=%s WHERE id=%s;", (STATE_TRAINING, modelID))
        database.commit()

        outputPipe = queue.Queue(8)

        def onMessage(message):
            outputPipe.put(message)

        def onFinished(isSucceed):
            if isSucceed:
                # update model state to training
                session = database.cursor()
                session.execute("UPDATE models SET state=%s WHERE id=%s;",
                                (STATE_MODEL_USABLE, modelID))
                database.commit()

                outputPipe.put("Done! Model successfully trained and saved.")
            else:
                # training failed. revert to last step
                session = database.cursor()
                session.execute("UPDATE models SET state=%s WHERE id=%s;",
                                (STATE_DATA_FEEDING, modelID))
                database.commit()

                outputPipe.put("Failed!")

            outputPipe.put(None)  # terminate outputstream to client
            print("Model " + str(modelID) + " is trained...successfully?", isSucceed)

        threading.Thread(target=solutionPlugins[pluginID]["instance"].trainModel,
                         args=(database, modelID, trainingParameter, onMessage, onFinished)).start()

        def events():
            message = outputPipe.get()
            while message is not None:
                yield message + "\n"
                message = outputPipe.get()

        res = Response(events(), mimetype='text/plain')
        res.headers["X-Content-Type-Options"] = "nosniff"
        return res

    @app.route('/predict', methods=['GET', 'POST'])
    def uploadPhotoAndPredict():
        if request.method == 'POST':
            files = request.files.getlist("file[]")
            modelName = request.form["modelID"]

            # get modelID from given id or nickname
            session = database.cursor()
            try:
                queryModelID = int(modelName)
                queryModelNickName = None
            except BaseException:
                queryModelID = -1
                queryModelNickName = modelName

            session.execute(
                "SELECT id, plugin_id, state FROM models WHERE id=%s OR nickname=%s;",
                (queryModelID,
                 queryModelNickName))
            result = session.fetchone()
            session.close()

            if result is None:
                return "No model with given modelID was found.", 404

            modelID, pluginID, modelState = result

            if modelState != STATE_MODEL_USABLE:
                return "Can't predict with a untrained model.", 400

            # deal with gives files
            print("DEBUG ", len(files), "files uploading.")
            resources = []
            resourceNames = []

            for file in files:
                if file and utils.isFileAllowed(file.filename, ALLOWED_EXTENSIONS):
                    mimetype = file.mimetype
                    if len(mimetype) < 3:  # mime type is invalid, guess it
                        mimetype = _getMimeFromExtension(file.filename)

                    if mimetype.startswith("image/"):
                        # load image
                        opencvImage = cv.imdecode(np.fromstring(
                            file.read(), np.uint8), cv.IMREAD_COLOR)

                        if opencvImage is None:
                            print("DEBUG Image", file.filename, "decode failed.")
                            continue

                        resources.append(opencvImage)
                        resourceNames.append(file.filename)

                        # print("DEBUG Image", image.filename,"upload OK.")
                    else:
                        print(
                            "DEBUG Resource",
                            file.filename,
                            "upload rejected. Not supported currently.")

                else:
                    print("DEBUG Resource", file.filename, "upload rejected.")

            outputPipe = queue.Queue(1)

            def onFinished(resultList):
                outputPipe.put(resultList)

            threading.Thread(target=solutionPlugins[pluginID]["instance"].predictWithData,
                             args=(database, modelID, resourceNames, resources, onFinished)).start()

            def events():
                predictResult = outputPipe.get()
                yield json.dumps(predictResult)

            return Response(events(), mimetype='application/json')

        return '''
            <!doctype html>
            <title>Upload new File to predit</title>
            <h1>Upload new File</h1>
            <form action="" method=post enctype=multipart/form-data>
                <input type=text name="modelName"/>
                <input type=file name="file[]" multiple="multiple"/>
                <input type=submit value=Upload />
            </form>
            '''

    @app.route('/predict_w_list', methods=['POST'])
    def feedJSONResouceIDListAndPredict():
        modelName = request.args.get('modelID')  # can be number: modelID, or model nickname

        resourceIDList = None

        if request.is_json:
            resourceIDList = request.get_json()
            if resourceIDList is None or not isinstance(resourceIDList, list):
                return "Bad resource list format.", 400

        # get modelID from given id or nickname
        session = database.cursor()
        try:
            queryModelID = int(modelName)
            queryModelNickName = None
        except BaseException:
            queryModelID = -1
            queryModelNickName = modelName

        session.execute(
            "SELECT id, plugin_id, state FROM models WHERE id=%s OR nickname=%s;",
            (queryModelID,
             queryModelNickName))
        result = session.fetchone()
        session.close()

        if result is None:
            return "No model with given modelID was found.", 404

        modelID, pluginID, modelState = result

        if modelState != STATE_MODEL_USABLE:
            return "Can't predict with a untrained model.", 400

        outputPipe = queue.Queue(1)

        def onFinished(resultList):
            outputPipe.put(resultList)

        threading.Thread(target=solutionPlugins[pluginID]["instance"].predictWithID,
                         args=(database, modelID, resourceIDList, onFinished)).start()

        def events():
            predictResult = outputPipe.get()
            yield json.dumps(predictResult)

        return Response(events(), mimetype='application/json')
