import socket
import time
import json


class Camera:

    def __init__(self, address='pylos.palomar.caltech.edu', port=5001):
        """

        :param address:
        :param port:
        """

        self.address = address
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.address, self.port))

    def __send_command(self, cmd="", parameters=None, timeout=300,
                       return_before_done=False):
        """

        :param cmd: string command to send to the camera socket
        :param parameters: list of parameters associated with cmd
        :param timeout: timeout in seconds for waiting for a command
        :return: Tuple (bool,string)
        """
        start = time.time()
        try:
            if timeout:
                self.socket.settimeout(timeout)

            if parameters:
                send_str = json.dumps({'command': cmd,
                                       'parameters': parameters})
            else:
                send_str = json.dumps({'command': cmd})
                
            self.socket.send(b"%s" % send_str.encode('utf-8'))

            if return_before_done:
                return {"elaptime": time.time()-start,
                        "data": "exiting the loop early"}

            data = self.socket.recv(2048)
            counter = 0
            while not data:
                time.sleep(.01)
                data = self.socket.recv(2048)
                counter += 1
                if counter > 100:
                    break
            return json.loads(data.decode('utf-8'))
        except Exception as e:
            return {'elaptime': time.time()-start,
                    'error': str(e)}

    def initialize(self):
        return self.__send_command(cmd="INITIALIZE")

    def shutdown(self):
        return self.__send_command(cmd="SHUTDOWN")

    def status(self):
        return self.__send_command(cmd="STATUS")

    def prefix(self):
        return self.__send_command(cmd="PREFIX")

    def take_image(self, shutter='normal', exptime=0.0, readout=2.0,
                   save_as="", return_before_done=False):

        parameters = {'shutter': shutter, "exptime": exptime,
                      "readout": readout, "save_as": save_as}

        return self.__send_command(cmd="TAKE_IMAGE", parameters=parameters,
                                   return_before_done=return_before_done)

    def listen(self):
        data = self.socket.recv(2048)
        counter = 0
        while not data:
            time.sleep(.1)
            data = self.socket.recv(2048)
            counter += 1
            if counter > 100:
                break
        return json.loads(data.decode('utf-8'))


if __name__ == '__main__':
    rc = Camera(address='localhost', port=5002)
    print(rc.initialize())
    print(rc.take_image(exptime=1, save_as='',
                        return_before_done=False))
    print(rc.status())
    print(rc.status())
    print(rc.shutdown())
    print(rc.socket.close())