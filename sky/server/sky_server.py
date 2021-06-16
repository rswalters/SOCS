import os
import json
import time
import socket
import threading
from sky.astrometry import solver
from sky.targets.scheduler import dbscheduler
from sky.astrometry.sextractor import run
from sky.guider import rcguider
from sky.targets.marshals import interface
from sky.targets.marshals.growth import marshal
import yaml

from utils.sedmlogging import setup_logger
from utils.message_server import (message_handler, response_handler,
                                  error_handler)

# Open the config file
SR = os.path.abspath(os.path.dirname(__file__) + '/../../')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)

# Setup logger
name = "skyLogger"
logfile = os.path.join(params['logging']['logpath'], 'sky_server.log')
logger = setup_logger(name, log_file=logfile)


class SkyServer:
    def __init__(self, hostname, port, do_connect=True):
        self.hostname = hostname
        self.port = port
        self.socket = ""
        self.cam = None
        self.sex = run.Sextractor()
        self.do_connect = do_connect
        self.scheduler = None #dbscheduler.Scheduler()
        self.marshals = marshal.interface()
        self.guider = rcguider.Guide(do_connect=do_connect)

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
                if data['command'].upper() == 'GETOFFSETS':
                    ret = solver.calculate_offset(**data['parameters'])
                elif data['command'].upper() == 'REINT':
                    self.sex = run.Sextractor()
                    self.scheduler = dbscheduler.Scheduler()
                    self.marshals = interface
                    self.guider = rcguider.Guide(do_connect=self.do_connect)
                    ret = {'elaptime': time.time()-starttime,
                                'data': 'System reinitialized'}
                elif data['command'].upper() == 'GETCALIBREQUESTID':
                    ret = self.scheduler.get_calib_request_id(**data['parameters'])
                elif data['command'].upper() == "GETSTANDARD":
                    ret = self.scheduler.get_standard(**data['parameters'])
                elif data['command'].upper() == "GETFOCUSCOORDS":
                    ret = self.scheduler.get_focus_coords(**data['parameters'])
                elif data['command'].upper() == "GETRCFOCUS":
                    ret = self.sex.run_loop(**data['parameters'])
                elif data['command'].upper() == 'STARTGUIDER':
                    ret = self.guider.start_guider(**data['parameters'])
                    ret = {"elaptime": time.time()-starttime, "data": "guider started"}
                elif data['command'].upper() == 'GETTARGET':
                    ret = self.scheduler.get_next_observable_target(**data['parameters'])
                elif data['command'].upper() == 'PING':
                    ret = {'elaptime': time.time()-starttime,
                            'data': 'PONG'}
                elif data['command'].upper() == "UPDATEGROWTH":
                    ret = self.marshals.update_status_request(**data['parameters'])
                elif data['command'].upper() == "UPDATEREQUEST":
                    ret = self.scheduler.update_request(**data['parameters'])
                elif data['command'].upper() == "GETGROWTHID":
                    ret = self.marshals.get_marshal_id_from_pharos(**data['parameters'])
                elif data['command'].upper() == 'GETTWILIGHTEXPTIME':
                    ret = self.scheduler.get_twilight_exptime(**data['parameters'])

            else:
                ret = {'elaptime': time.time()-starttime,
                       'error': "Command not found"}

            response = response_handler(ret, inputdata=data,
                                        starttime=starttime)
            logger.info("Response: %s", response)
            jsonstr = json.dumps(response)
            connection.sendall(jsonstr.encode('utf-8'))

    def start(self):
        logger.debug("Sky server now listening for connections on port:%s" % self.port)
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
    server = SkyServer("localhost", 5004, do_connect=False)
    # try:
    logger.info("Starting IFU Server")
    server.start()
    # except Exception as e:
    #    print(str(e))
    #    logging.exception("Unexpected exception %s", str(e))
    # finally:
    #    logging.info("Shutting down IFU server")
    logger.info("All done")
