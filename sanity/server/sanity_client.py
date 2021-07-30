import socket
import time
import json


class Sanity:

    def __init__(self, address='localhost', port=5005):
        """

        :param camera:
        :param address:
        :param port:
        """

        self.address = address
        self.port = port
        print(self.address, self.port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.address, self.port))

    def __send_command(self, cmd="", parameters=None, timeout=600,
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
                time.sleep(.1)
                data = self.socket.recv(2048)
                counter += 1
                if counter > 100:
                    break
            return json.loads(data.decode('utf-8'))
        except Exception as e:
            return {'elaptime': time.time() - start, 'error': str(e)}

    def check_for_files(self, camera, keywords, data_dir="",
                        return_before_done=False):
        parameters = {
            'camera': camera,
            'keywords': keywords,
            'data_dir': data_dir
        }

        return self.__send_command(cmd="CHECKFORFILES",
                                   return_before_done=return_before_done,
                                   parameters=parameters)

    def check_socket(self):
        """
        Try sending a command to the camera program
        :return:(bool,response)
        """
        return self.__send_command(cmd="PING")

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
    rc = Sky()
    s = time.time()
    print(rc.get_next_observable_target())
    print(time.time()-s)