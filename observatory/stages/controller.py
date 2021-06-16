import logging
from logging.handlers import TimedRotatingFileHandler
import time
import socket
import os
import json

SITE_ROOT = os.path.abspath(os.path.dirname(__file__)+'/../..')

with open(os.path.join(SITE_ROOT, 'config', 'logging.json')) as data_file:
    params = json.load(data_file)

logger = logging.getLogger("stageControllerLogger")
logger.setLevel(logging.DEBUG)
logging.Formatter.converter = time.gmtime
formatter = logging.Formatter("%(asctime)s--%(name)s--%(levelname)s--"
                              "%(module)s--%(funcName)s--%(message)s")

logHandler = TimedRotatingFileHandler(os.path.join(params['abspath'],
                                                   'stage_controller.log'),
                                      when='midnight', utc=True, interval=1,
                                      backupCount=360)
logHandler.setFormatter(formatter)
logHandler.setLevel(logging.DEBUG)
logger.addHandler(logHandler)
logger.info("Starting Logger: Logger file is %s", 'stage_controller.log')



class Stage:
    """The following stage controller commands are available. Note that many
    are not implemented at the moment.

    AC Set/Get acceleration
    BA  Set/Get backlash compensation
    BH  Set/Get hysteresis compensation
    DV  Set/Get driver voltage Not for PP
    FD  Set/Get low pass filter for Kd Not for PP
    FE  Set/Get following error limit Not for PP
    FF  Set/Get friction compensation Not for PP
    FR  Set/Get stepper motor configuration Not for CC
    HT  Set/Get HOME search type
    ID  Set/Get stage identifier
    JD  Leave JOGGING state
    JM  Enable/disable keypad
    JR  Set/Get jerk time
    KD  Set/Get derivative gain Not for PP
    KI  Set/Get integral gain Not for PP
    KP  Set/Get proportional gain Not for PP
    KV  Set/Get velocity feed forward Not for PP
    MM  Enter/Leave DISABLE state
    OH  Set/Get HOME search velocity
    OR  Execute HOME search
    OT  Set/Get HOME search time-out
    PA  Move absolute
    PR  Move relative
    PT  Get motion time for a relative move
    PW  Enter/Leave CONFIGURATION state
    QI  Set/Get motor’s current limits
    RA  Get analog input value
    RB  Get TTL input value
    RS  Reset controller
    SA  Set/Get controller’s RS-485 address
    SB  Set/Get TTL output value
    SC  Set/Get control loop state Not for PP
    SE  Configure/Execute simultaneous started move
    SL  Set/Get negative software limit
    SR  Set/Get positive software limit
    ST  Stop motion
    SU  Set/Get encoder increment value Not for PP
    TB  Get command error string
    TE  Get last command error
    TH  Get set-point position
    TP  Get current position
    TS  Get positioner error and controller state
    VA  Set/Get velocity
    VB  Set/Get base velocity Not for CC
    VE  Get controller revision information
    ZT  Get all axis parameters
    ZX  Set/Get SmartStage configuration

    """

    def __init__(self, host=None, port=None):
        """
        Class to handle communications with the stage controller and any faults

        :param simulated: bool, Run in a simulated mode
        :param address: tuple, ip of stage socket and port socket
        """


        with open(os.path.join(SITE_ROOT, 'config', 'stages.json')) as data_file:
            self.stage_config = json.load(data_file)

        if not host:
            self.host = self.stage_config['host']
        else:
            self.host = host
        if not port:
            self.port = self.stage_config['port']
        else:
            self.port = port

        logger.info("Initiating stage controller on host:"
                    " %(host)s port: %(port)s", {'host': self.host, 'port': self.port})

        self.socket = socket.socket()

        self.controller_commands = ["PA", "SU", "ZX1", "ZX2", "ZX3", "OR",
                                    "PW1", "PW0", "SL", "SR", "SU", "HT1",
                                    "TS", "TP", "ZT", "RS"]

        self.return_value_commands = ["ts", "tp"]
        self.parameter_commands = ["pa", "SU"]
        self.state_commands = ["ts?"]
        self.end_code_list = ['32', '33', '34', '35']
        self.not_ref_list = ['0A', '0B', '0C', '0D', '0F', '10', '11']
        self.msg = {
            "0A": "NOT REFERENCED from reset.",
            "0B": "NOT REFERENCED from HOMING.",
            "0C": "NOT REFERENCED from CONFIGURATION.",
            "0D": "NOT REFERENCED from DISABLE.",
            "0E": "NOT REFERENCED from READY.",
            "0F": "NOT REFERENCED from MOVING.",
            "10": "NOT REFERENCED ESP stage error.",
            "11": "NOT REFERENCED from JOGGING.",
            "14": "CONFIGURATION.",
            "1E": "HOMING commanded from RS-232-C.",
            "1F": "HOMING commanded by SMC-RC.",
            "28": "MOVING.",
            "32": "READY from HOMING.",
            "33": "READY from MOVING.",
            "34": "READY from DISABLE.",
            "35": "READY from JOGGING.",
            "3C": "DISABLE from READY.",
            "3D": "DISABLE from MOVING.",
            "3E": "DISABLE from JOGGING.",
            "46": "JOGGING from READY.",
            "47": "JOGGING from DISABLE."
        }

    def __connect(self):
        try:
            logger.info("Connected to %(host)s:%(port)s", {'host': self.host,
                                                           'port': self.port})
            self.socket.connect((self.host, self.port))
        except Exception as e:
            logger.info("Error connecting to the socket", exc_info=True)
            return str(e)

    def __decode_response(self, message_id):
        try:
            msg = self.msg[message_id]
            logger.info(msg)
            return msg
        except Exception as e:
            logger.error("Error decoding response", exc_info=True)
            return str(e)

    def __send_serial_command(self, stage_id=1, msg=''):
        """

        :param stage_id:
        :param msg:
        :param decode_response:
        :return:
        """
        cmd = "%s%s\r\n" % (stage_id, msg)
        logger.info("Sending command:%s", cmd)
        x = cmd.encode('utf-8')
        self.__connect()
        self.socket.settimeout(30)
        self.socket.send(x)
        time.sleep(.05)

        if msg.lower() in self.return_value_commands:

            recv = self.socket.recv(2048)
            print(recv, len(recv), "In return vale")
            if len(recv) == 11 or len(recv) == 12 or len(recv)==13:
                print("This is a value command")
                return recv
        t = 300

        # Now handle wait commands
        while t > 0:
            statecmd = '%sTS\r\n' % stage_id
            statecmd = statecmd.encode('utf-8')
            self.socket.send(statecmd)
            time.sleep(.05)
            recv = self.socket.recv(1024)

            if len(recv) == 11:
                recv = recv.rstrip()
                code = recv[-2:].decode('utf-8')
                if str(code) in self.end_code_list:
                    return recv
                elif str(code) in self.not_ref_list:
                    return recv
            else:
                code = "33"
                if str(code) in self.end_code_list:
                    return recv
                elif str(code) in self.not_ref_list:
                    return recv
            t -= 1

        print(recv)
        return recv

    def __send_command(self, cmd="", parameters=None, stage_id=1,
                       custom_command=False, home_when_not_ref=True):
        """
        Send a command to the stage controller and keep checking the state
        until it matches one in the end_code

        :param cmd: string command to send to the camera socket
        :param parameters: list of parameters associated with cmd
        :param timeout: timeout in seconds for waiting for a command
        :return: Tuple (bool,string)
        """
        start = time.time()

        if not custom_command:
            if cmd.rstrip().upper() not in self.controller_commands:
                return {'elaptime': time.time()-start, 'error': "%s is not a valid command" % cmd}


        print(cmd, self.parameter_commands, 3)
        # Check if the command should have parameters
        if cmd in self.parameter_commands and parameters:
            print("add parameters")
            parameters = [str(x) for x in parameters]
            parameters = " ".join(parameters)
            cmd += parameters
            print(cmd)

        # Next check if we expect a return value from command

        response = self.__send_serial_command(stage_id, cmd)
        response = response.decode('utf-8')
        print("Cmd response from stage controller 1", response, cmd)

        message = self.__return_parse(response)

        print(type(cmd), cmd, len(cmd), 'cmd values')
        if cmd not in self.return_value_commands and self.__return_parse(response) == "Unknown state":
            return {'elaptime': time.time() - start, 'error': response}

        elif cmd in self.return_value_commands:

            print(cmd.lower(), "this is the command")
            if cmd.lower() == 'tp':
                response = response.rstrip()
                return {'elaptime': time.time() - start, 'data': response[3:]}

            else:
                return {'elaptime': time.time() - start, 'data': message}

        elif 'REFERENCED' in message:
            if home_when_not_ref:
                print("NOT REF")
                response = self.__send_serial_command(stage_id, 'OR')
                response = response.decode('utf-8')
                print("Cmd response from stage controller", response)
                message = self.__return_parse(response)
                return {'elaptime': time.time() - start, 'data': message}

            else:
                return {'elaptime': time.time() - start, 'error': message}

        else:
            return {'elaptime': time.time() - start, 'data': message}


        #except Exception as e:
       #     print("Error in the stage controller return")
       #     print(str(e))
       #     return -1 * (time.time() - start), str(e)

    def __return_parse(self, message=""):
        """
        Parse the return message from the controller.  The message code is
        given in the last two string characters

        :param message: message code from the controller
        :return: string message
        """
        message = message.rstrip()
        code = message[-2:]
        return self.msg.get(code, "Unknown state")

    def enterConfigState(self,stage_id=1):
        """

        :param stage_id:
        :return:
        """
        cmd = ""
        end_code = None

        print("WARNING YOU ARE ABOUT TO ENTER THE CONFIGURATION STATE.\n"
              "PLEASE DON'T MAKE ANY CHANGES UNLESS YOU KNOW WHAT YOU ARE DOING")
        input("Press Enter to Continue")

        message = ("Choose the number to change the configuration state. 1. Set HOME position\n"
              "2. Set negative software limit\n"
              "3. Set positive software limit\n"
              "4. Set encoder increment value\n"
              "5. Use custom command\n"     
              "6.Save and Exit Configuration State\n")

         
        value = int(input("Choose Configuration to Change"))

        if value == 6:
            print("Exiting configuration")
            return
        custom_command = False

        ret = self.__send_command(cmd='PW1', stage_id=stage_id,
                                   end_code=["32", "33", "34", "35", "14"])

        print(ret)
        while True:

            if value == 0:
                print(message)
                value = int(input("Choose Configuration to Change"))

            if value == 1:
                cmd = "HT1"

            elif value == 2:
                cmd = "SL"
                value = input("Enter value between -10^12 to 0")

            elif value == 3:
                cmd = "SR"
                value = input("Enter value between 0 to 10^12")

            elif value == 4:
                cmd = "SU"
                value = input("Enter value between 10^-6 to 10^12")

            elif value == 5:
                cmd = input("Enter custom command")
                custom_command = True
            elif value == 6:
                ret = self.__send_command(cmd='PW0', stage_id=stage_id)
                break
            else:
                print("Value not recognized exiting")
                ret = self.__send_command(cmd='PW0', stage_id=stage_id)
                return

            print(ret, value, custom_command)

            ret = self.__send_command(cmd=cmd, stage_id=stage_id,
                                      custom_command=custom_command)
            print(ret)
            value = 0
            print(value)
            time.sleep(3)
            custom_command = False




    def move_focus(self, position=12.5, stage_id=1):
        """
        Move stage focus and return when in position

        :return:bool, status message
        """
        return self.__send_command(cmd="pa", stage_id=stage_id, parameters=[position])

    def set_encoder_value(self, value=12.5, stage_id=1):
        """
        Move stage focus and return when in position

        :return:bool, status message
        """
        return self.__send_command(cmd="SU", stage_id=stage_id, parameters=[value])


    def home(self, stage_id=1):
        """
        Home the stage
        :return: bool, status message
        """
        return self.__send_command(cmd='OR', stage_id=stage_id)
    def get_all(self, stage_id=1):
        """
        Home the stage
        :return: bool, status message
        """
        return self.__send_command(cmd='ZT', stage_id=stage_id)
    def disable_esp(self, stage_id=1):
        """
        Home the stage
        :return: bool, status message
        """
        return self.__send_command(cmd='ZX1', stage_id=stage_id)

    def enable_esp(self, stage_id=1):
        """
        Home the stage
        :return: bool, status message
        """
        return self.__send_command(cmd='ZX3', stage_id=stage_id)

    def get_state(self, stage_id=1):
        return self.__send_command(cmd="ts", stage_id=stage_id)

    def get_position(self, stage_id=1):
        start = time.time()
        try:
            x = self.__send_command(cmd="tp", stage_id=stage_id)
        except Exception as e:
            print(str(e), 'get_position error')
            x = {'elaptime': time.time()-start, 'error': 'Unable to send stage command'}
        return x

    def reset(self, stage_id=1):
        return self.__send_command(cmd="RS")

    def get_limits(self, stage_id=1):
        return self.__send_command(cmd="ZT")

    def run_manually(self, stage_id=1):
        while True:

            cmd = input("Enter Command")

            if not cmd:
                break

            ret = self.__send_command(cmd=cmd, stage_id=stage_id, custom_command=True)
            print(ret, "End")

if __name__ == "__main__":
    s = Stage()
    #print(s.get_limits(stage_id=2))
    #print(s.get_position(stage_id=1))
    #print(s.disable_esp(1))
    #time.sleep(3)


    #s.run_manually(1)
    #s.enterConfigState(1)
    #print(s.home(1))
    #print(s.reset(1))
    #print(s.enable_esp(1))
    #print(s.set_encoder_value(value=.000244140625, stage_id=1))
    #print(s.get_all(1))
    #time.sleep(5)
    #print(s.home(1))
    #time.sleep(4)
    #print(s.move_focus(.4, stage_id=1))
    #print(s.move_focus(2.5, stage_id=2))
    #print(s.home(1))
    print(s.get_position(2))
    print(s.get_state(1))
    #print(s.home(2))
    #print(s.move_focus(3.5, stage_id=2))
    #time.sleep(1)
    #print(s.get_position(stage_id=2))

    #print(s.home(1))
    #print(s.move_focus(.52, stage_id=1))
    #print(s.get_position(stage_id=1))

    #print(s.home(2))
    #print(s.move_focus(5.0, stage_id=2))
    #print(s.get_position(stage_id=2))