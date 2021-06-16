import logging
from logging.handlers import TimedRotatingFileHandler
import json
import os
import time
import socket
import threading


SITE_ROOT = os.path.abspath(os.path.dirname(__file__)+'/../..')

with open(os.path.join(SITE_ROOT, 'config', 'logging.json')) as data_file:
    params = json.load(data_file)

logger = logging.getLogger("stageSimLogger")
logger.setLevel(logging.DEBUG)
logging.Formatter.converter = time.gmtime
formatter = logging.Formatter("%(asctime)s--%(name)s--%(levelname)s--"
                              "%(module)s--%(funcName)s--%(message)s")

logHandler = TimedRotatingFileHandler(os.path.join(params['abspath'],
                                                   'stage_simserver.log'),
                                      when='midnight', utc=True, interval=1,
                                      backupCount=360)
logHandler.setFormatter(formatter)
logHandler.setLevel(logging.DEBUG)
logger.addHandler(logHandler)
logger.info("Starting Logger: Logger file is %s", 'stage_simserver.log')


class SimServer:
    def __init__(self, hostname, port):
        self.hostname = hostname
        self.port = port
        self.socket = ""
        self.cam = None
        self.pset = "pset"

    def handle(self, connection, address):
        while True:
            response = {'test': 'test'}
            try:

                data = connection.recv(2048)

                data = data.decode("utf8")
                logger.info("Received: %s", data)
                if not data:
                    break
                print(type(data), data)
                print(type(self.pset))
                print(data, self.pset)
                if self.pset in data:

                    x = data.split()
                    if x[2] == "1":
                        ret = '\xff\xfd\x03\xff\xfb\x01\r\nSynaccess Inc. Telnet Session V6.2\n\r>\r\n>pset %s 1\n\r' % x[1]
                    elif x[2] == "0":
                        ret = '\xff\xfd\x03\xff\xfb\x01\r\nSynaccess Inc. Telnet Session V6.2\n\r>\r\n>pset %s 0\n\r' % x[1]
                elif "pshow" in data:
                    ret = '\xff\xfd\x03\xff\xfb\x01\r\nSynaccess Telnet V6.2\n\r>\r\n>pshow\n\r\n\r\n\rPort | Name       |Status\n\r   1 |    Outlet1 |   OFF|   2 |    Outlet2 |   ON |\r\n>\x00'
                else:
                    ret = 'Dont know'

                print(ret)
                connection.sendall(ret.encode('utf-8'))
            except Exception as e:
                print(str(e))
                logger.error("Big ERROR", exc_info=True)
                pass

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
    server = SimServer("localhost", 8000)
    # try:
    logger.info("Starting Lamp Sim Server")
    server.start()
    # except Exception as e:
    #    print(str(e))
    #    logging.exception("Unexpected exception %s", str(e))
    # finally:
    #    logging.info("Shutting down IFU server")
    logger.info("All done")
