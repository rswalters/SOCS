import socket
import time
import json


class Observatory:
    def __init__(self, address='localhost',  port=5003):
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
                time.sleep(.5)
                data = self.socket.recv(2048)
                counter += 1
                if counter > 100:
                    break

            return json.loads(data.decode('utf-8'))
        except Exception as e:
            return {'elaptime': time.time() - start,
                    'error': str(e)}

    # INITIALIZE COMMANDS
    def initialize_ocs(self):
        return self.__send_command(cmd="INITIALIZE_ALL")

    def initialize_lamps(self):
        return self.__send_command(cmd="INITIALIZE_LAMPS")

    def initialize_stages(self):
        return self.__send_command(cmd="INITIALIZE_STAGES")

    def initialize_tcs(self):
        return self.__send_command(cmd="INITIALIZE_TCS")

    def check_socket(self):
        """
        Try sending a command to the camera program
        :return:(bool,response)
        """
        return self.__send_command(cmd="PING")

    # STATUS COMMANDS
    def check_status(self):
        x = self.__send_command(cmd="OBSSTATUS")
        return x

    def check_faults(self):
        return self.__send_command(cmd="TELFAULTS")

    def check_pos(self):
        return self.__send_command(cmd="OBSPOS")

    def check_weather(self):
        return self.__send_command(cmd="OBSWEATHER")

    # STAGE COMMANDS
    def move_stage(self, position=3.3, stage_id=1):
        parameters = {
            'position': position,
            'stage_id': stage_id
        }
        return self.__send_command(cmd="STAGEMOVE",
                                   parameters=parameters)

    def stage_position(self, stage_id):
        parameters = {
            'stage_id': stage_id
        }
        return self.__send_command(cmd="STAGEPOSITION",
                                   parameters=parameters)

    def stage_home(self, stage_id):
        parameters = {
            'stage_id': stage_id
        }
        return self.__send_command(cmd="STAGEHOME",
                                   parameters=parameters)

    # TCS COMMANDS
    def halogens_on(self):
        return self.__send_command(cmd="TELHALON", return_before_done=False)

    def take_control(self):
        return self.__send_command(cmd="TAKECONTROL")

    def halogens_off(self):
        return self.__send_command(cmd="TELHALOFF", return_before_done=False)

    def telx(self):
        return self.__send_command(cmd="TELX")

    def tel_offset(self, ra=0, dec=0):
        parameters = {
            'ra': ra,
            'dec': dec
        }
        return self.__send_command(cmd="TELOFFSET", parameters=parameters)

    def goto_focus(self, pos=14.26):
        parameters = {
            'pos': pos
        }
        return self.__send_command(cmd="TELGOFOC", parameters=parameters)

    def set_rates(self, ra=0, dec=0):
        parameters = {
            'ra': ra,
            'dec': dec
        }
        return self.__send_command(cmd="SETRATES", parameters=parameters)

    def tel_move(self, name='Test', ra=None, dec=None, equinox=2000,
                 ra_rate=0, dec_rate=0, motion_flag="", epoch=""):

        ra = float(ra)/15
        dec = float(dec)

        parameters = {
            'name': name,
            'ra': ra,
            'dec': dec,
            'equinox': equinox,
            'ra_rate': ra_rate,
            'dec_rate': dec_rate,
            'motion_flag': motion_flag,
            'epoch': epoch,
        }

        return self.__send_command(cmd="TELMOVE", parameters=parameters)

    def stow(self, ha=0, dec=109, domeaz=40):
        parameters = {
            'ha': ha,
            'dec': dec,
            'domeaz': domeaz
        }
        return self.__send_command(cmd="TELSTOW", parameters=parameters)

    def dome(self, state):
        parameters = {
            'state': state
        }
        return self.__send_command(cmd="DOME",
                                   parameters=parameters)

    # LAMP COMMANDS
    def arclamp(self, lamp="", command="", force_check=True):
        start = time.time()
        command = command.upper()
        if command == "ON":
            parameters = {
                'lamp': lamp
            }
            return self.__send_command(cmd="ARCLAMPON",
                                       parameters=parameters)
        elif command == "OFF":
            parameters = {
                'lamp': lamp
            }
            return self.__send_command(cmd="ARCLAMPOFF",
                                       parameters=parameters)

        elif command == "STATUS":
            parameters = {
                'lamp': lamp,
                'force_check':  force_check
            }
            return self.__send_command(cmd="ARCLAMPSTATUS",
                                       parameters=parameters)
        else:
            return {"elaptime": time.time()-start,
                    "error": "Arclamp command not known"}

    # STAGE COMMANDS
    def stage_position(self, stage_id):
        parameters = {
            'stage_id': stage_id
        }
        return self.__send_command(cmd="STAGEPOSITION",
                                   parameters=parameters)

if __name__ == '__main__':
    ocs = Observatory()
    print(ocs.initialize_ocs())
    #print(ocs.goto_focus(15.44))
    print(ocs.arclamp('hg', 'OFF'))
    #print(ocs.stage_position(1))
    #x = {}
    #y = ocs.check_status()
    #x.update(y['data'])
    #y = ocs.check_weather()
    #x.update(y['data'])
    #y = ocs.check_pos()
    #x.update(y['data'])
    #print(x)
