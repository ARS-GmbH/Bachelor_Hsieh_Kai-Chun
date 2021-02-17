"""
Copyright (c) 2020 ARS Computer & Consulting GmbH

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
"""

import abc, time, datetime

MESSAGE_TYPE_TEXT = 0  # Enum. Set Message payload type to text-messages.
MESSAGE_TYPE_IMAGE = 1 # Enum. Set Message payload type to image-messages.

class Notification(abc.ABC):
    """
    Interface of a notification class.
    """

    @abc.abstractmethod
    def __enter__(self):
        pass

    @abc.abstractmethod
    def __exit__(self, exeType, exeValue, exeTraceback):
        pass

    @abc.abstractmethod
    def sendMessage(self, messageType, payload):
        """
        Send a message.

        Args: 
            messageType (int): Type of the message in the payload.
            payload (obj): payload.
        """
        pass

class ConsoleNotification(Notification):
    """
    A notificator print notifications directly on a console.
    """

    def __enter__(self):
        pass

    def __exit__(self, exeType, exeValue, exeTraceback):
        pass

    
    def sendMessage(self, messageType, payload):
        """
        Print notification directly on the console if payload is a text message, otherwise, save incoming message under CWD and print a text message on the console.

        Args:
            messageType (int): type of the payload. Either MESSAGE_TYPE_TEXT or MESSAGE_TYPE_IMAGE currently
        """

        if MESSAGE_TYPE_TEXT == messageType:
            print(">>>>>>>>>>>>>>>>>>> Text Message at", datetime.datetime.now(), ":", payload)

        elif MESSAGE_TYPE_IMAGE == messageType:
            filename = "consolenotification-" + str(time.time_ns()) + ".png"
            print(">>>>>>>>>>>>>>>>>>> Image Message at", datetime.datetime.now(), "Saved as", filename)

            with open(filename, "wb") as file:
                file.write(payload.read())


import paho.mqtt.client as mqttClient

class MQTTNotification(Notification):
    """
    A notificator sending notifications via MQTT.
    """

    def __init__(self, brokerAddress, brokerPort, username, password, clientID, topicID):
        self._brokerAddress = brokerAddress
        self._brokerPort = brokerPort
        self._username = username
        self._password = password
        self._clientID = clientID
        self._topicID = topicID
        self._connected = False

    def __enter__(self):
        self._client = mqttClient.Client(self._clientID)                            #create new instance
        self._client.username_pw_set(self._username, password=self._password)       #set username and password

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print("DEBUG Connected to MQTT-Broker")
                self._connected = True                                              #Signal connection 
            else:
                print("Connection failed")
        self._client.on_connect= on_connect                                         #attach function to callback

        #self._client.on_message= on_message 

        def on_log(client, userdata, level, buf):
            print("DEBUG MQTT LOG: ", buf)
        #self._client.on_log=on_log

        self._client.connect(self._brokerAddress, port=self._brokerPort)            #connect to broker
        self._client.loop_start()                                                   #start the loop

        while self._connected != True:                                              #Wait for connection
            time.sleep(0.1)

    def __exit__(self, exeType, exeValue, exeTraceback):
        self._client.disconnect()
        self._client.loop_stop()

    def sendMessage(self, messageType, payload):
        """
        Send notification directly via MQTT protocol if payload is a text message, otherwise save incoming message under CWD and send a text message via MQTT.

        Args:
            messageType (int): type of the payload. Supports MESSAGE_TYPE_TEXT and MESSAGE_TYPE_IMAGE currently.
        """

        if MESSAGE_TYPE_TEXT == messageType:
            print(">>>>>>>>>>>>>>>>>>> Text Message at", datetime.datetime.now(), ":", payload)

            self._client.publish(self._topicID, payload, qos=2)

        elif MESSAGE_TYPE_IMAGE == messageType:
            filename = "mqttnotification-" + str(time.time_ns()) + ".png"
            print(">>>>>>>>>>>>>>>>>>> Image Message at", datetime.datetime.now(), "Saved as", filename)

            with open(filename, "wb") as file:
                file.write(payload.read())
            self._client.publish(self._topicID, "Image Message Saved as " + filename, qos=2)