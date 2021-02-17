"""
Copyright (c) 2020 ARS Computer & Consulting GmbH

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
"""

def getPluginName(plugin):
    return plugin.getManufacturer() + "_" + plugin.getName()


def getPluginID(plugin):
    return plugin.getManufacturer() + "_" + plugin.getName() + "_" + plugin.getVersion()


def getPluginDataTableID(pluginID):
    return pluginID.replace(".", "_")


def isFileAllowed(filename, allowedExtension):
    filename = filename.lower()
    return '.' in filename and filename.rsplit('.', 1)[1] in allowedExtension


def reserveNewID(database, moduleTag):
    session = database.cursor()
    session.execute("UPDATE resource_indexes\
                        SET next_index = next_index + 1\
                     WHERE module_id = '" + moduleTag + "' RETURNING next_index;")

    database.commit()

    return session.fetchone()[0] - 1
