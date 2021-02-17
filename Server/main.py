"""
Copyright (c) 2020 ARS Computer & Consulting GmbH

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
"""

from flask import Flask
import psycopg2

database = psycopg2.connect(database="postgres", user="postgres", password="postgres", host="127.0.0.1", port="5432")

#initialize global setting datatable
session = database.cursor()
session.execute("CREATE TABLE IF NOT EXISTS resource_indexes\
                (\
                    module_id text NOT NULL,\
                    next_index integer NOT NULL,\
                    PRIMARY KEY (module_id)\
                )\
                WITH (\
                    OIDS = FALSE\
                );")
database.commit()

app = Flask(__name__)

# initialize different modules
import server_api 
serverAPI = server_api.ServerAPI()

import resource_loader
resource_loader.initialize(database, app, serverAPI)

import solution_manager
solution_manager.initialize(database, app, serverAPI)


if __name__ == "__main__":
    app.run()