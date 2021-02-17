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
import mimetypes
import cv2
from flask import jsonify, make_response, request

# static parameters
MODULE_TAG_RESOURCE = "resource_manager"

ALLOWED_EXTENSIONS = ['png', 'jpg', 'jpeg', 'bmp']

# global runtime parameters
resourcePlugins = {} 
mimeCache = {}


def initialize(database, app, serverAPI):
    # initialize resource database
    session = database.cursor()
    session.execute("CREATE TABLE IF NOT EXISTS resources\
                    (\
                        id integer NOT NULL,\
                        created_at timestamp without time zone NOT NULL,\
                        create_by text NOT NULL,\
                        plugin_id text NOT NULL,\
                        mime      text NOT NULL,\
                        PRIMARY KEY (id)\
                    )\
                    WITH (\
                        OIDS = FALSE\
                    );")
    database.commit()

    # initialize resource index
    session = database.cursor()
    session.execute("INSERT INTO resource_indexes (module_id, next_index)\
                    SELECT '" + MODULE_TAG_RESOURCE + "', 0\
                    WHERE NOT EXISTS (SELECT 1 FROM resource_indexes WHERE module_id = '" + MODULE_TAG_RESOURCE + "');")
    database.commit()

    # load resource loaders
    for plugin in os.listdir("./resource_loader_plugins"):
        pluginFilename = plugin

        if pluginFilename.endswith(".py") and not pluginFilename.startswith("interface") and not pluginFilename.startswith("__init__"):
            pluginModule = importlib.import_module(
                "resource_loader_plugins." + pluginFilename[:-3])

            try:
                pluginClass = pluginModule.reflector()
            except:
                print("ERROR Resource plugin", pluginFilename,
                      "was refused to load: ERR_NO_REFLECTOR_METHOD")
                continue

            try:
                instanceID = utils.getPluginID(pluginClass)
            except:
                print("ERROR Resource plugin", pluginFilename,
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
                                    extra_info json,\
                                    PRIMARY KEY (id)\
                                )\
                                WITH (\
                                    OIDS = FALSE\
                                );")
                database.commit()

            except:
                print("ERROR Resource plugin", pluginFilename,
                      "was refused to load: ERR_DATATABLE_CREATE_FAILED")
                continue

            resourcePlugins[instanceID] = {"instance": pluginClass(
                databaseID, serverAPI), "class": pluginClass}

    print("INFO", len(resourcePlugins), "resource plugins loaded.")

    @app.route('/resource_pluigins', methods=['GET'])
    def resourceLoaderInfoProvider():
        loaders = []
        for loader in resourcePlugins:
            pluginClass = resourcePlugins[loader]["class"]

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

    @app.route('/upload', methods=['GET', 'POST'])
    def dataUploader():
        if request.method == 'POST':
            files = request.files.getlist("file[]")
            pluginName = request.form["plugin_name"]

            print("DEBUG", len(files), "files uploading.")

            uploadOK = []
            uploadFailed = []
            uploadNotallowed = []

            if pluginName and (pluginName in resourcePlugins):
                for file in files:

                    if file and utils.isFileAllowed(file.filename, ALLOWED_EXTENSIONS):
                        mime = file.mimetype
                        if len(mime) < 3:  # mime type is invalid, guess it
                            mime = _getMimeFromExtension(file.filename)

                        newID = utils.reserveNewID(
                            database, MODULE_TAG_RESOURCE)
                        result = resourcePlugins[pluginName]["instance"].putResource(
                            database, newID, file, mime)

                        if result:
                            print("DEBUG Plugin", pluginName,
                                  "saved a resource successfully: " + file.filename)

                            # update resource record
                            session = database.cursor()
                            session.execute("INSERT INTO resources (id, created_at, create_by, plugin_id, mime) VALUES (%s, NOW(), %s, %s, %s)", (
                                newID, "webuser0", pluginName, mime))
                            database.commit()

                            resourceIDMap = {}
                            resourceIDMap[newID] = file.filename
                            uploadOK.append(resourceIDMap)

                        else:
                            print("ERROR", pluginName,
                                  "failed to store a uploaded photo.")
                            uploadFailed.append(file.filename)
                    else:
                        print("ERROR file", file.filename,
                              ", file type is not allowed.")
                        uploadNotallowed.append(file.filename)

                return jsonify({"OK": uploadOK, "FAILED": uploadFailed, "NOT-ALLOWED": uploadNotallowed}), 200
            else:
                return "Plugin " + pluginName + " not found.", 404

        return '''
            <!doctype html>
            <title>Upload new File</title>
            <h1>Upload new File</h1>
            <form action="" method=post enctype=multipart/form-data>
                <input type=text name=plugin_name />
                <input type=file name="file[]" multiple="multiple"/>
                <input type=submit value=Upload />
            </form>
            '''

    @app.route('/get_resource_metadata/<resourceID>', methods=['GET'])
    def resourceMetadataGetter(resourceID):
        record, err = getResourceMetadata(database, resourceID)

        if err:
            if err == "err_not_found":
                return "Not found.", 404

            elif err == "err_plugin_removed":
                return "Plugin handling this resource has been removed.", 410

            elif err == "err_plugin_record_removed":
                return "Resource can no longer be found.", 410

            else:
                return "Unknown error.", 500

        return jsonify(record)

    @app.route('/get_resource_list', methods=['GET'])
    def resourceListGetter():
        return jsonify(getAllResourceMetadata(database))

    @app.route('/get_resource/<resourcID>', methods=['GET'])
    def resourceGetter(resourcID):

        resource, mime, err = getResource(database, resourcID)

        if err:
            if err == "err_not_found":
                return "Not found.", 404

            elif err == "err_plugin_removed":
                return "Plugin handling this resource has been removed.", 410

            elif err == "err_plugin_record_removed":
                return "Resource can no longer be found.", 410

            else:
                return "Unknown error.", 500

        if mime.startswith("image/"):
            _, buffer = cv2.imencode('.png', resource)
            response = make_response(buffer.tobytes())
            response.headers['Content-Type'] = 'image/png'
        else:
            return "Unknown format error.", 500

        return response

# APIs


def getResource(database, resourceID):
    # get the record
    session = database.cursor()
    session.execute(
        "SELECT created_at, create_by, mime, plugin_id FROM resources WHERE id=%s", (resourceID,))
    result = session.fetchone()
    session.close()

    if result:
        _, _, mime, pluginID = result
        if pluginID not in resourcePlugins:
            return None, None, "err_plugin_removed"

        plugin = resourcePlugins[pluginID]["instance"]
        resource = plugin.getResource(database, resourceID)

        if resource is None:
            return None, None, "err_plugin_record_removed"

        return resource, mime, None

    else:
        return None, None, "err_not_found"


def getResourceMetadata(database, resourceID):
    # get the record
    session = database.cursor()
    session.execute(
        "SELECT created_at, create_by, mime, plugin_id FROM resources WHERE id=%s", (resourceID,))
    result = session.fetchone()
    session.close()

    if result:
        createdAt, createBy, mime, pluginID = result

        if pluginID not in resourcePlugins:
            return None, "err_plugin_removed"

        plugin = resourcePlugins[pluginID]["instance"]
        extraInfo = plugin.getResourceExtraInfo(database, resourceID)

        if extraInfo:
            return {"CREATED-AT": createdAt, "CREATED-BY": createBy, "PLUGIN-ID": pluginID, "EXTRA-INFO": extraInfo, "MIME": mime}, None
        else:
            return None, "err_plugin_record_removed"

    else:
        return None, "err_not_found"


def getAllResourceMetadata(database):
    # get the record
    session = database.cursor()
    session.execute(
        "SELECT id, created_at, create_by, plugin_id, mime FROM resources ORDER BY id DESC;")
    result = session.fetchall()
    session.close()

    resourceLists = []

    for resource in result:
        resourceID, createdAt, createBy, pluginID, mime = resource

        if pluginID in resourcePlugins:

            plugin = resourcePlugins[pluginID]["instance"]
            extraInfo = plugin.getResourceExtraInfo(database, resourceID)

            if extraInfo:
                resourceLists.append({"ID": resourceID, "CREATED-AT": createdAt, "CREATED-BY": createBy,
                                      "PLUGIN-ID": pluginID, "MIME": mime, "EXTRA-INFO": extraInfo})

    return resourceLists


def _getMimeFromExtension(filename):

    if filename in mimeCache:
        return mimeCache[filename]
    else:
        typeGuess, _ = mimetypes.guess_type(filename)
        if typeGuess:
            mimeCache[filename] = typeGuess
            return typeGuess
        else:
            return None
