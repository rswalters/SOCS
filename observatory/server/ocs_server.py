import os
import logging
import json
from logging.handlers import TimedRotatingFileHandler
import time
from observatory.arclamps import controller as lamps
from observatory.stages import controller as stages
from observatory.telescope import tcs
import socket
import threading

import yaml

from utils.sedmlogging import setup_logger
from utils.message_server import (message_handler, response_handler,
                                  error_handler)

# Open the config file
SR = os.path.abspath(os.path.dirname(__file__) + '/../../')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)

# Setup logger
name = "ocsLogger"
logfile = os.path.join(params['logging']['logpath'], 'ocs_server.log')
logger = setup_logger(name, log_file=logfile)


class ocsServer:
    def __init__(self, hostname, port):
        self.hostname = hostname
        self.port = port
        self.socket = ""
        self.stages = None
        self.lamp_controller = None
        self.lamps_dict = None
        self.tcs = None

    def handle(self, connection, address):
        while True:
            starttime = time.time()
            data = message_handler(connection, starttime=starttime)
            ret = ''
            logger.info("Data Received: %s", data)

            # Check the data return if it's False then there was an error and
            # we should exit the loop.  Or if the data is not in dictionary
            # form then we should exit
            if isinstance(data, bool) or not isinstance(data, dict):
                print(data, "Bad return from message_handler")
                print(connection, address)
                break
                
            if 'command' in data:
                if 'parameters' in data:
                    parameters = data['parameters']
                else:
                    parameters = {}

                if data['command'].upper() == 'INITIALIZE_ALL':
                    ret = ''
                    if not self.lamp_controller:
                        logger.info("Initializing Arc Lamps")
                        self.lamp_controller = True
                        self.lamps_dict = lamps.connect_all()
                        ret += 'Lamps Connected\n'
                    if not self.stages:
                        logger.info("Initializing Stages")
                        self.stages = stages.Stage()
                        ret += 'Stages initialized\n'
                    if not self.tcs:
                        logger.info("Initializing Telescope")
                    self.tcs = tcs.Telescope()
                    ret += 'Telescope initialized\n'
                    ret = {'elaptime': time.time() - starttime,
                                'data': ret}

                elif data['command'].upper() == 'INITIALIZE_LAMPS':
                    if not self.lamp_controller:
                        logger.info("Initializing Arc Lamps")
                        self.lamp_controller = lamps.Lamp()
                    ret = "Lamps initialized"
                elif data['command'].upper() == 'INITIALIZE_STAGES':
                    if not self.stages:
                        logger.info("Initializing Stages")
                        self.stages = stages.Stage()
                    ret = "Stages initialized"
                elif data['command'].upper() == 'INITIALIZE_TCS':
                    if not self.tcs:
                        logger.info("Initializing Telescope")
                        self.tcs = tcs.Telescope()
                    ret = "Telescope initialized"
                elif data['command'].upper() == "OBSSTATUS":
                    ret = self.tcs.get_status()
                elif data['command'].upper() == "OBSWEATHER":
                    ret = self.tcs.get_weather()
                elif data['command'].upper() == "OBSPOS":
                    ret = self.tcs.get_pos()
                elif data['command'].upper() == "TELMOVE":
                    ret = self.tcs.tel_move_sequence(**parameters)
                elif data['command'].upper() == "TELOFFSET":
                    ret = self.tcs.offset(**parameters)
                elif data['command'].upper() == "TELGOFOC":
                    ret = self.tcs.gofocus(**parameters)
                elif data['command'].upper() == "TELOFFSETFOC":
                    ret = self.tcs.incfocus(**parameters)
                elif data['command'].upper() == "TELFAULTS":
                    ret = self.tcs.get_faults()
                elif data['command'].upper() == "TELX":
                    ret = self.tcs.x()
                elif data['command'].upper() == "TAKECONTROL":
                    ret = self.tcs.takecontrol()
                elif data['command'].upper() == "TELHALON":
                    ret = self.tcs.halogens_on()
                elif data['command'].upper() == "TELX":
                    ret = self.tcs.x()
                elif data['command'].upper() == "TELHALOFF":
                    ret = self.tcs.halogens_off()
                elif data['command'].upper() == "TELSTOW":
                    ret = self.tcs.stow(**parameters)
                elif data['command'].upper() == "DOME":
                    ret = self.tcs.dome(**parameters)
                elif data['command'].upper() == "SETRATES":
                    ret = self.tcs.irates(**parameters)
                elif data['command'].upper() == "ARCLAMPON":
                    ret = self.lamps_dict[parameters['lamp']].on()
                elif data['command'].upper() == "ARCLAMPOFF":
                    ret = self.lamps_dict[parameters['lamp']].off()
                elif data['command'].upper() == "ARCLAMPSTATUS":
                    ret = self.lamps_dict[parameters['lamp']].status(parameters['force_check'])
                elif data['command'].upper() == "STAGEMOVE":
                    ret = self.stages.move_focus(**parameters)
                elif data['command'].upper() == "STAGEPOSITION":
                    ret = self.stages.get_position(**parameters)
                elif data['command'].upper() == "STAGESTATE":
                    ret = self.stages.get_state(**parameters)
                elif data['command'].upper() == "STAGEHOME":
                    ret = self.stages.home(**parameters)
                elif data['command'].upper() == "PING":
                    ret = {'elaptime': time.time()-starttime,
                           'data': 'PONG'}
                else:
                    ret = {"elaptime": time.time()-starttime,
                           "error": "Command not found"}
            else:
                ret = {'elaptime': time.time()-starttime,
                       'error': "Command not found"}

            response = response_handler(ret, inputdata=data,
                                        starttime=starttime)
            logger.info("Response: %s", response)
            jsonstr = json.dumps(response)
            connection.sendall(jsonstr.encode('utf-8'))

    def start(self):
        logger.debug("IFU server now listening for connections on port:%s" % self.port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(None)
        self.socket.bind((self.hostname, self.port))
        self.socket.listen(5)

        while True:
            conn, address = self.socket.accept()
            logger.debug("Got connection from %s:%s" % (conn, address))
            new_thread = threading.Thread(target=self.handle, args=(conn, address))
            new_thread.start()
            logger.debug("Started process")


if __name__ == "__main__":
    server = ocsServer("localhost", 5003)
    # try:
    logger.info("Starting IFU Server")
    server.start()
    # except Exception as e:
    #    print(str(e))
    #    logging.exception("Unexpected exception %s", str(e))
    # finally:
    #    logging.info("Shutting down IFU server")
    logger.info("All done")



