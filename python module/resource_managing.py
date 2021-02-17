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
import numbers

class ResourceList:
    """
    A class maintaining list of resources.
    """

    def __init__(self, resourceIDMapList):
        """
        Constructor.

        Args:
            resourceIDMapList (obj): Can be either List<int>, list of resourceIDs. Or Dict<int, str>, Dict of resourceID to its original filenames.
        """

        self._resourceIDMapList = resourceIDMapList
        self._IDs = []

        if len(resourceIDMapList) > 0 and isinstance(resourceIDMapList[0], numbers.Number):
            self._IDs = resourceIDMapList

        else:
            for entry in resourceIDMapList:
                idEntrys = entry.keys()
                if len(idEntrys) != 1:
                    raise ValueError("Bad server response formate at: " + str(entry))

                for idEntry in idEntrys:
                    self._IDs.append(idEntry)

    def getIDs(self):
        """
        Get ID of the resources tracking by this instance.

        Returns:
            idList (List<int>): List of the resourceIDs.
        """
        return self._IDs

    def getResourceIDFilenameMap(self):
        """
        Get the map of resourceIDs to their original filename.

        Returns:
            resourceIDMapList (obj): Either List<int> or Dict<int, str>
        """

        return self._resourceIDMapList

    def merge(self, another):
        """
        Merge this instance with another.

        Args:
            another (ResourceList): another instance.
        """

        listFromAnother = another.getIDs()
        self._resourceIDMapList = {**self._resourceIDMapList, **self.getResourceIDFilenameMap()}
        self._IDs += listFromAnother

        return self


class ResourceManager:
    """
    A Clever-Lab AI server resource manager.
    """

    def __init__(self, address, port):
        """
        Constructor.
        
        Args:
            address (str): IP or URL of the server.
            port (str): Port of the server.
        """

        self._address = address
        self._port = port

    def getPluginList(self, table_view = False):
        """
        Get the list of resource management plugins installed  on the server.

        Args:
            table_view (bool): Whether render response with table-view.

        Returns:
            response (obj): Json by default; pandas Dataframe by table-view mdoe. Contains columns: id, name, manufacturer, version, description and price description.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        res = requests.get("http://" + self._address + ":" + str(self._port) + "/resource_pluigins")
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

    def uploadResources(self, pluginID, resourceFileList):
        """
        Upload resources with a list of files.

        Args:
            pluginID (str): ID of the plugin handles this uploading.
            resourceFileList (List<str>): List of filenames of uploading resources.

        Returns:
            response (obj): A _UploadResourceResult object, containing fields uploaded, rejected, failed.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        files = []

        for resourceFile in resourceFileList:
            file = open(resourceFile, "rb")

            files.append(("file[]", (resourceFile, file)))
        
        res = requests.post("http://" + self._address + ":" + str(self._port) + "/upload", files=files, data={"plugin_name": pluginID})

        if res.status_code == 200:
            content = res.json()
            return _UploadResourceResult(content["OK"], content["FAILED"], content["NOT-ALLOWED"])

        elif res.status_code == 404:
            raise RuntimeError("Plugin not found: " + res.text)

        else:
            raise RuntimeError("Unknown error: " + res.text +", with status " + str(res.status_code) + "")

    def getResourceList(self, table_view = False):
        """
        Get the list of resources created on the server.

        Args:
            table_view (bool): Whether render response with table-view.

        Returns:
            response (obj): Json by default; pandas Dataframe by table-view mdoe. Contains columns: ID, CREATED-BY, CREATED-AT, PLUGIN-ID, MIME, EXTRA_INFO.

        Raises:
            RuntimeError: If failed to fetch valid response from server.
        """

        res = requests.get("http://" + self._address + ":" + str(self._port) + "/get_resource_list")
        if res.status_code == 200:

            if table_view:
                tableHeaders = ["id", "created by", "created at", "upload-plugin id", "resource type", "extra-info"]
                data = [] 

                for resource in res.json():
                    data.append([resource["ID"], resource["CREATED-BY"], resource["CREATED-AT"], resource["PLUGIN-ID"], resource["MIME"],resource["EXTRA-INFO"]])
                
                return pandas.DataFrame(data, columns = tableHeaders)

            else:
                return res.json()

        else:
            raise RuntimeError("Unknown error code: " + str(res.status_code))

# Privte classes

class _UploadResourceResult:
    def __init__(self, filesOK, filesFailed, filesNotAllowed):
        self.uploaded = ResourceList(filesOK)
        self.failed = filesFailed
        self.rejected = filesNotAllowed