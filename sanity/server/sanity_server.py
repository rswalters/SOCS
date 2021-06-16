import os
import logging
import json
from logging.handlers import TimedRotatingFileHandler
import time
import socket
import threading
from utils import fileChecker

SITE_ROOT = os.path.abspath(os.path.dirname(__file__)+'/../..')

with open(os.path.join(SITE_ROOT, 'config', 'logging.json')) as data_file:
    params = json.load(data_file)

logger = logging.getLogger("sanityLogger")
logger.setLevel(logging.DEBUG)
logging.Formatter.converter = time.gmtime
formatter = logging.Formatter("%(asctime)s--%(name)s--%(levelname)s--"
                              "%(module)s--%(funcName)s--%(message)s")

logHandler = TimedRotatingFileHandler(os.path.join(params['abspath'],
                                                   'sanity_server.log'),
                                      when='midnight', utc=True, interval=1,
                                      backupCount=360)
logHandler.setFormatter(formatter)
logHandler.setLevel(logging.DEBUG)
logger.addHandler(logHandler)
logger.info("Starting Logger: Logger file is %s", 'sanity_server.log')


class SanityServer:
    def __init__(self, hostname, port):
        self.hostname = hostname
        self.port = port
        self.socket = ""
        self.files = fileChecker.Checker()

    def handle(self, connection, address):
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
                    if data['command'].upper() == 'CHECKFORFILES':
                        response = self.files.check_for_images(**data['parameters'])
                else:
                    response = {'elaptime': time.time()-start,
                                'error': "Command not found"}
                jsonstr = json.dumps(response)
                connection.sendall(jsonstr.encode('utf-8'))
            except Exception as e:
                logger.error("Big error", exc_info=True)
                pass

    def start(self):
        logger.debug("Sanity server now listening for connections on port:%s" % self.port)
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
    server = SanityServer("localhost", 5005)
    # try:
    logger.info("Starting Sanity Server")
    server.start()
    # except Exception as e:
    #    print(str(e))
    #    logging.exception("Unexpected exception %s", str(e))
    # finally:
    #    logging.info("Shutting down IFU server")
    logger.info("All done")
