import os
import json
import time
import socket
import threading
from cameras.pixis import interface as pixis
from utils.message_server import (message_handler, response_handler,
                                  error_handler)
from utils.sedmlogging import setup_logger
import yaml

# Open the config file
SR = os.path.abspath(os.path.dirname(__file__)+'/../../')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)

# Setup logger
name = "cameraLogger"
logfile = os.path.join(params['logging']['logpath'], 'camera_server.log')
logger = setup_logger(name, log_file=logfile)


class CamServer:
    def __init__(self, hostname, port, send_data=False):
        """
        Camera server class
        :param hostname: str for host to run the server on
        :param port: int for tcp port communication
        """
        self.hostname = hostname
        self.port = port
        self.socket = None
        self.cam = None
        self.send_data = send_data
        self.output_dir = params['setup']['image_dir']

        # TODO Move this over to the configuration file
        if self.port == 5002:
            self.cam_prefix = "rc"
        else:
            self.cam_prefix = "ifu"
        print("Starting up cam server on %s port %s" % (self.hostname, self.port))

    def handle(self, connection, address):
        print(connection, address)
        logger.info("Incoming:%s %s" % (connection, address))
        while True:
            starttime = time.time()
            data = message_handler(connection, starttime=starttime)
            logger.info("Data Received: %s", data)

            # Check the data return if it's False then there was an error and
            # we should exit the loop.  Or if the data is not in dictionary
            # form then we should exit
            if isinstance(data, bool) or not isinstance(data, dict):
                print(data, "Bad return from message_handler")
                print(connection, address)
                break

            #  Check to see what action to preform
            if data['command'].upper() == 'INITIALIZE':
                # The camera has not been initialized then self.cam will
                # still be None.
                if not self.cam:
                    self.cam = pixis.Controller(serial_number="",
                                                cam_prefix=self.cam_prefix,
                                                send_to_remote=self.send_data,
                                                output_dir=self.output_dir)

                    ret = self.cam.initialize()
                    # If no data was returned or it was False then we should
                    # check to see what the last error was on the camera
                    if not ret:
                        error_dict = error_handler('Problem initializing '
                                                   'camera: %s' %
                                                   self.cam.lastError,
                                                   inputdata=data,
                                                   starttime=starttime)
                        connection.sendall(error_dict)
                        print("I am still in the loop")
                        break
                else:
                    ret = 'Camera already initialized'
            elif data['command'].upper() == 'TAKE_IMAGE':
                print("Taking an image")
                ret = self.cam.take_image(**data['parameters'])
            elif data['command'].upper() == 'STATUS':
                ret = self.cam.get_status()
            elif data['command'].upper() == 'PING':
                ret = {'data': 'PONG'}
            elif data['command'].upper() == "LASTERROR":
                ret = self.cam.lastError
            elif data['command'].upper() == "LASTEXPOSED":
                ret = self.cam.lastExposed
            elif data['command'].upper() == "PREFIX":
                ret = self.cam.camPrefix
            elif data['command'].upper() == "REINIT":
                ret = self.cam.opt.disconnect()
            elif data['command'].upper() == "SHUTDOWN":
                ret = [self.cam.opt.disconnect(), self.cam.opt.unloadLibrary()]
                self.cam = None
            else:
                ret = 'Command: %s not found' % data['command']

            response = response_handler(ret, inputdata=data,
                                        starttime=starttime)
            logger.info("Response: %s", response)
            jsonstr = json.dumps(response)
            connection.sendall(jsonstr.encode('utf-8'))

        connection.close()
        logger.info("Connection closed")

    def start(self):
        """
        Run the server for accepting incoming commands
        :return:
        """
        logger.debug("IFU server now listening for connections on port:%s" % self.port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(None)
        self.socket.bind((self.hostname, self.port))
        self.socket.listen(5)

        while True:
            if os.path.exists(params['commands']['stop_file']):
                break
            conn, address = self.socket.accept()
            logger.debug("Got connection from %s:%s" % (conn, address))
            new_thread = threading.Thread(target=self.handle, args=(conn, address))
            new_thread.start()
            logger.debug("Started process")


if __name__ == "__main__":
    server = CamServer("localhost", 5002)
    # try:
    logger.info("Starting RC Server")
    server.start()
    # except Exception as e:
    #    print(str(e))
    #    logging.exception("Unexpected exception %s", str(e))
    # finally:
    #    logging.info("Shutting down IFU server")
    logger.info("All done")
