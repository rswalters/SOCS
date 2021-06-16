import logging
from logging.handlers import TimedRotatingFileHandler
import json
import os
import time
import socket
import threading
import yaml

SR = os.path.abspath(os.path.dirname(__file__)+'/../../')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)

logger = logging.getLogger("tcsSimLogger")
logger.setLevel(logging.DEBUG)
logging.Formatter.converter = time.gmtime
formatter = logging.Formatter("%(asctime)s--%(name)s--%(levelname)s--"
                              "%(module)s--%(funcName)s--%(message)s")
logfile = os.path.join(params['logging']['logpath'], 'tcs_simserver.log')
logHandler = TimedRotatingFileHandler(logfile,
                                      when='midnight', utc=True, interval=1,
                                      backupCount=360)
logHandler.setFormatter(formatter)
logHandler.setLevel(logging.DEBUG)
logger.addHandler(logHandler)
logger.info("Starting Logger: Logger file is %s", 'tcs_simserver.log')

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
                    ret = '\xff\xfd\x03\xff\xfb\x01\r\nSynaccess Telnet V6.2\n\r>\r\n>pshow\n\r\n\r\n\rPort | Name       |Status\n\r   1 |    Outlet1 |   OFF|   2 |    Outlet2 |   OFF |\r\n>\x00'
                elif 'status' in data.lower():
                    ret = """?STATUS:
UTC=2019:245:12:13:02.0
Telescope_ID=60
Telescope_Control_Status=REMOTE
Lamp_Status=OFF
Lamp_Current=0.00
Dome_Shutter_Status=CLOSED
WS_Motion_Mode=BOTTOM
Dome_Motion_Mode=ANTICIPATE
Telescope_Power_Status=READY
Oil_Pad_Status=READY
Weather_Status=OKAY
Sunlight_Status=OKAY
Remote_Close_Status=NOT_OKAY
Telescope_Ready_Status=READY
HA_Axis_Hard_Limit_Status=OKAY
Dec_Axis_Hard_Limit_Status=OKAY
Focus_Hard_Limit_Status=OKAY
Focus_Soft_Up_Limit_Value=35.00
Focus_Soft_Down_Limit_Value=0.50
Focus_Soft_Limit_Status=OKAY
Focus_Motion_Status=STATIONARY
East_Soft_Limit_Value=-6.4
West_Soft_Limit_Value=6.4
North_Soft_Limit_Value=109.5
South_Soft_Limit_Value=-41.8
Horizon_Soft_Limit_Value=10.0
HA_Axis_Soft_Limit_Status=OKAY
Dec_Axis_Soft_Limit_Status=OKAY
Horizon_Soft_Limit_Status=OKAY"""

                elif 'pos' in data.lower() and 'go' not in data.lower():
                    ret = """?POS:
UTC=2019:245:12:13:02.2
LST=03:11:01.3
Julian_Date=2458729.0090534
Apparent_Equinox=2019.67
Telescope_Equinox=J2000.0
Telescope_HA=E00:51:28.85
Telescope_RA=04:01:38.90
Telescope_Dec=-20:31:56.3
Telescope_RA_Rate=0.00
Telescope_Dec_Rate=0.00
Telescope_RA_Offset=13166.08
Telescope_Dec_Offset=-110.87
Telescope_Azimuth=165.34
Telescope_Elevation=34.84
Telescope_Parallactic=347
Telescope_HA_Speed=-0.0046
Telescope_Dec_Speed=0.0000
Telescope_HA_Refr(arcsec)=-15.25
Telescope_Dec_Refr(arcsec)=-65.88
Telescope_Motion_Status=STOPPED
Telescope_Airmass=1.747
Telescope_Ref_UT=11.840406
Object_Name="Simulated"
Object_Equinox=J2000.0
Object_RA=03:46:01.55
Object_Dec=-20:30:27.9
Object_RA_Rate=0.00
Object_Dec_Rate=0.00
Object_RA_Proper_Motion=0.000000
Object_Dec_Proper_Motion=0.00000
Focus_Position=15.81
Dome_Gap(inch)=-240
Dome_Azimuth=233.3
Windscreen_Elevation=0
UTSunset=02:31
UTSunrise=13:00
Solar_RA=10:44
Solar_Dec=+07:58
"""

                elif 'weather' in data.lower():
                    ret = """?WEATHER:
UTC=2019:245:12:13:02.1
Windspeed_Avg_Threshold=25.0
Gust_Speed_Threshold=35.0
Gust_Hold_Time=900
Outside_DewPt_Threshold=2.0
Inside_DewPt_Threshold=2.0
Wetness_Threshold=500
Wind_Dir_Current=63
Windspeed_Current=3.7
Windspeed_Average=5.7
Outside_Air_Temp=20.5
Outside_Rel_Hum=65.7
Outside_DewPt=13.9
Inside_Air_Temp=21.3
Inside_Rel_Hum=55.9
Inside_DewPt=12.1
Mirror_Temp=21.2
Floor_Temp=21.7
Bot_Tube_Temp=21.0
Mid_Tube_Temp=21.3
Top_Tube_Temp=21.4
Top_Air_Temp=21.3
Primary_Cell_Temp=21.2
Secondary_Cell_Temp=21.2
Wetness=-271
Weather_Status=READY"""

                else:
                    ret = "0"

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
    server = SimServer("localhost", 9002)
    # try:
    logger.info("Starting Lamp Sim Server")
    server.start()
    # except Exception as e:
    #    print(str(e))
    #    logging.exception("Unexpected exception %s", str(e))
    # finally:
    #    logging.info("Shutting down IFU server")
    logger.info("All done")
