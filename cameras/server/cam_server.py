import os
import logging
import json
from logging.handlers import TimedRotatingFileHandler
import time
import socket
import threading
from cameras.pixis import interface as pixis
import yaml

SR = os.path.abspath(os.path.dirname(__file__)+'/../../')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)

logger = logging.getLogger("cameraLogger")
logger.setLevel(logging.DEBUG)
logging.Formatter.converter = time.gmtime
formatter = logging.Formatter("%(asctime)s--%(name)s--%(levelname)s--"
                              "%(module)s--%(funcName)s--%(message)s")

logfile = os.path.join(params['logging']['logpath'], 'camera_server.log')
logHandler = TimedRotatingFileHandler(logfile, when='midnight', utc=True,
                                      interval=1, backupCount=360)
logHandler.setFormatter(formatter)
logHandler.setLevel(logging.DEBUG)
logger.addHandler(logHandler)
logger.info("Starting Logger: Logger file is %s", 'camera_controller.log')


class CamServer:
    def __init__(self, hostname, port):
        """
        Camera server class
        :param hostname: str for host to run the server on
        :param port: int for tcp port communication
        """
        self.hostname = hostname
        self.port = port
        self.socket = None
        self.cam = None
        print("Starting up cam server on %s port %s" % (self.hostname, self.port))

    def handle(self, connection, address):
        print(connection, address)
        logger.info("Incoming:%s %s" % (connection, address))
        while True:
            response = {'test': 'test'}
            try:
                start = time.time()
                data = connection.recv(2048)

                data = data.decode("utf8")
                logger.info("Received: %s", data)

                if not data:
                    break
                print(data)
                try:
                    data = json.loads(data)
                except Exception as e:
                    logger.error("Load error", exc_info=True)
                    error_dict = json.dumps({'elaptime': time.time()-start,
                                             "error": "error message %s" % str(e)})
                    connection.sendall(error_dict)
                    break

                if 'command' in data:
                    if data['command'].upper() == 'INITIALIZE':
                        if not self.cam:
                            if self.port == 5002:
                                cam_prefix = "rc"
                                send_to_remote = False
                                output_dir = params['setup']['image_dir']
                            else:
                                cam_prefix = "ifu"
                                send_to_remote = False
                                output_dir = params['setup']['image_dir']
                            self.cam = pixis.Controller(serial_number="",
                                                        cam_prefix=cam_prefix,
                                                        send_to_remote=send_to_remote,
                                                        output_dir=output_dir)

                            ret = self.cam.initialize()
                            if self.port == 5002:
                                self.cam.serialNumber = "04001312"
                            else:
                                self.cam.serialNumber = "05313416"
                            if ret:
                                response = {'elaptime': time.time()-start,
                                            'data': "Camera started"}
                            else:
                                response = {'elaptime': time.time()-start,
                                            'error': self.cam.lastError}
                        else:
                            print(self.cam)
                            print(type(self.cam))
                            response = {'elaptime': time.time()-start,
                                        'data': "Camera already intiailzed"}

                    elif data['command'].upper() == 'TAKE_IMAGE':
                        response = self.cam.take_image(**data['parameters'])
                    elif data['command'].upper() == 'STATUS':
                        response = self.cam.get_status()
                    elif data['command'].upper() == 'PING':
                        response = {'data': 'PONG'}
                    elif data['command'].upper() == "LASTERROR":
                        response = self.cam.lastError
                    elif data['command'].upper() == "LASTEXPOSED":
                        response = self.cam.lastExposed
                    elif data['command'].upper() == "PREFIX":
                        response = {'elaptime': time.time()-start,
                                    'data': self.cam.camPrefix}
                    elif data['command'].upper() == "REINIT":
                        response = self.cam.opt.disconnect()
                    elif data['command'].upper() == "SHUTDOWN":
                        ret = self.cam.opt.disconnect()
                        ret = self.cam.opt.unloadLibrary()
                        self.cam = None
                        response = {'elaptime': time.time()-start,
                                    'data': "Camera shutdown"}
                else:
                    response = {'elaptime': time.time()-start,
                                'error': "Command not found"}
                jsonstr = json.dumps(response)
                connection.sendall(jsonstr.encode('utf-8'))
            except Exception as e:
                logger.error("Big error", exc_info=True)
                pass

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
            if os.path.exists('/home/rsw/cam_stop.txt'):
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
