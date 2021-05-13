import time
import datetime
from cameras.pixis.picamLib import *
from astropy.io import fits
#from utils.transfer_to_remote import transfer
import yaml
import os
from utils.sedmlogging import setup_logger

SR = os.path.abspath(os.path.dirname(__file__)+'/../../')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)

name = "pixisLogger"
logfile = os.path.join(params['logging']['logpath'], 'pixis_controller.log')
logger = setup_logger(name, logfile)

class Controller:
    def __init__(self, config_file=None, cam_prefix="rc", serial_number="",
                 output_dir="", parseport=5001,
                 force_serial=True, set_temperature=-40, send_to_remote=False,
                 remote_config='nemea.config.json'):
        """
        Initialize the controller for the PIXIS camera and
        :param cam_prefix:
        :param serial_number:
        :param output_dir:
        :param force_serial:
        :param set_temperature:
        """

        # Load the default parameters from config file
        if not config_file:
            config_file = os.path.join(SR, 'config',
                                       '%s_config.yaml' % cam_prefix)
            with open(config_file) as df:
                camera_params = yaml.load(df, Loader=yaml.FullLoader)
            self.__dict__.update(camera_params['default'].items())

        self.camPrefix = cam_prefix
        self.outputDir = output_dir
        self.forceSerial = force_serial
        self.setTemperature = set_temperature
        self.ExposureTime = 0
        self.lastExposed = None
        self.opt = None
        self.parseport = parseport
        self.send_to_remote = send_to_remote
        if self.send_to_remote:
            self.transfer = None #transfer(**params)
        self.lastError = ""

    def _set_output_dir(self):
        """
        Keep data separated by utdate.  Unless saveas is defined all
        files will be saved in a utdate directory in the output directory.
        :return: str output directory path
        """
        return os.path.join(self.outputDir,
                            datetime.datetime.utcnow().strftime("%Y%m%d"))

    def _set_shutter(self, shutter):
        # Start off by setting the shutter mode
        logger.info("Setting shutter to state:%s", shutter)
        # 1. Make sure shutter state is correct string format
        shutter = shutter.lower()
        shutter_list = []

        if shutter in self.shutter_dict:
            shutter_list.append(['ShutterTimingMode',
                                 PicamShutterTimingMode[self.shutter_dict[shutter]]])
            shutter_list.append(["ShutterClosingDelay", 0])
            return shutter_list
        else:
            logger.error('%s is not a valid shutter state', shutter, exc_info=True)
            self.lastError = '%s is not a valid shutter state' % shutter
            return False

    def _set_parameters(self, parameters, commit=True):
        """
        Set the parameters.  The return is the calculated readout time
        based on the active parameters.
        parameters: dictionary of Camera properties
        return: readout time in milliseconds
        """

        for param in parameters:
            self.opt.setParameter(param[0], param[1])

        if commit:
            self.opt.sendConfiguration()

        return self.opt.getParameter("ReadoutTimeCalculation")

    def initialize(self, path_to_lib=""):
        """
        Initialize the library and connect the cameras.  When no camera
        is detected the system opens a demo cam up for testing.

        :param path_to_lib: Location of the dll or .so library
        the camera is at it's set temperature
        :return: Bool (True if no errors)
        """

        # Initialize and load the PICAM library
        logger.info("Loading PICAM libaray")
        try:
            self.opt = picam()
            self.opt.loadLibrary(path_to_lib)
        except Exception as e:
            self.lastError = str(e)
            logger.error("Fatal error in main loop", exc_info=True)
            return False
        logger.info("Finished loading library")
        logger.info("Getting available cameras")

        # Get the available cameras and try to select the one desired by the
        # serial number written on the back of the cameras themselves
        camera_list = self.opt.getAvailableCameras()
        camera_list = [camera.decode('utf-8') for camera in camera_list]
        logger.info("Available Cameras:%s", camera_list)
        if self.serialNumber:
            if not self.forceSerial:
                try:
                    pos = camera_list.index(self.serialNumber)
                except Exception as e:
                    self.lastError = str(e)
                    logger.error("Camera %s is not in list", self.serialNumber, exc_info=True)
                    return False
            else:
                pos = None
        else:
            logger.info("No serial number given, using demo cam")
            pos = None
            self.serialNumber = 'Demo'

        logger.info("Connecting '%s' camera", self.serialNumber)

        # Connect the camera for operations
        try:
            self.opt.connect(pos)
        except Exception as e:
            self.lastError = str(e)
            logger.info("Unable to connect to camera:%s", self.serialNumber)
            logger.error("Connection error", exc_info=True)
            return False

        # Set the operating temperature and wait to cool the instrument
        # before continuing. We wait for this cooling to occur because
        # past experience has shown working with the cameras during the
        # cooling cycle can cause issues.
        logger.info("Setting temperature to: %s", self.setTemperature)
        self.opt.setParameter("SensorTemperatureSetPoint", self.setTemperature)
        self.opt.sendConfiguration()

        temp = self.opt.getParameter("SensorTemperatureReading")
        lock = self.opt.getParameter("SensorTemperatureStatus")

        while temp != self.setTemperature:
            logger.debug("Dector temp at %sC", temp)
            print(temp, lock)
            time.sleep(1)
            temp = self.opt.getParameter("SensorTemperatureReading")
            lock = self.opt.getParameter("SensorTemperatureStatus")

        while lock != 2:
            print(temp, lock)
            logger.debug("Wait for temperature lock to be set")
            lock = self.opt.getParameter("SensorTemperatureStatus")
            time.sleep(1)
            logger.info("Camera temperature locked in place. Continuing "
                        "initialization")

        # Set default parameters
        try:
            self.opt.setParameter("ActiveWidth", self.ActiveWidth)
            self.opt.setParameter("ActiveHeight", self.ActiveHeight)
            self.opt.setParameter("ActiveLeftMargin", self.ActiveLeftMargin)
            self.opt.setParameter("ActiveRightMargin", self.ActiveRightMargin)
            self.opt.setParameter("ActiveTopMargin", self.ActiveTopMargin)
            self.opt.setParameter("ActiveBottomMargin", self.ActiveBottomMargin)
            self.opt.sendConfiguration()
        except Exception as e:
            self.lastError = str(e)
            logger.error("Error setting default configuration", exc_info=True)
            return False

        # Set default Adc values
        try:
            self.opt.setParameter('AdcAnalogGain',
                                  PicamAdcAnalogGain[self.AdcAnalogGain])
            self.opt.setParameter('AdcQuality',
                                  PicamAdcQuality[self.AdcQuality])
            self.opt.setParameter('TimeStamps',
                                  PicamTimeStampsMask['ExposureStarted'])

            self.opt.sendConfiguration()
        except Exception as e:
            self.lastError = str(e)
            logger.error("Error setting the Adc values", exc_info=True)
            return False

        # Make sure the base data directory exists:
        if self.outputDir:
            if not os.path.exists(self.outputDir):
                self.lastError = "Image directory does not exists"
                logger.error("Image directory %s does not exists", self.outputDir)
                return False
        return True

    def get_status(self):
        """Simple function to return camera information that can be displayed
         on the website"""
        try:
            status = {
                    'camexptime': self.opt.getParameter("ExposureTime"),
                    'camtemp': self.opt.getParameter("SensorTemperatureReading"),
                    'camspeed': self.opt.getParameter("AdcSpeed"),
                    'state': self.opt.getParameter("OutputSignal")
            }
            logger.info(status)
            return status
        except Exception as e:
            logger.error("Error getting the camera status", exc_info=True)
            return {
                "error": str(e), "camexptime": -9999,
                "camtemp": -9999, "camspeed": -999
            }

    def get_camera_state(self, parameter):
        """Get the camera state"""
        return self.opt.getParameter(parameter)

    def take_image(self, shutter='normal', exptime=0.0,
                   readout=2.0, save_as="", timeout=None):
        """
        Set the camera parameters and then start the exposure sequence

        :param shutter:
        :param exptime:
        :param readout:
        :param save_as:
        :param timeout:
        :return: A dictionary with the path of the file or error message
                along with the elapsed time
        """

        s = time.time()
        parameter_list = []
        readout_time = 5
        exptime_ms = 0

        print(self.opt.getParameter('TimeStamps'), 'timestamp')
        # 1. Set the shutter state
        shutter_return = self._set_shutter(shutter)
        if shutter_return:
            parameter_list += shutter_return
        else:
            return {'elaptime': time.time()-s,
                    'error': "Error setting shutter state"}

        # 2. Convert exposure time to ms`
        try:
            exptime_ms = int(float(exptime) * 1000)
            logger.info("Converting exposure time %(exptime)ss"
                        " to %(exptime_ms)s"
                        "milliseconds", {'exptime': exptime,
                                         'exptime_ms': exptime_ms})
            parameter_list.append(['ExposureTime', exptime_ms])
        except Exception as e:
            self.lastError = str(e)
            logger.error("Error setting exposure time", exc_info=True)

        # 3. Set the readout speed
        logger.info("Setting readout speed to: %s", readout)
        if readout not in self.AdcSpeed_States:
            logger.error("Readout speed '%s' is not valid", readout)
            return {'elaptime': time.time()-s,
                    'error': "%s not in AdcSpeed states" % readout}
        parameter_list.append(['AdcSpeed', readout])

        # 4. Set parameters and get readout time
        try:
            logger.info("Sending configuration to camera")
            readout_time = self._set_parameters(parameter_list)
            r = int(readout_time) / 1000
            logger.info("Expected readout time=%ss", r)
        except Exception as e:
            self.lastError = str(e)
            logger.error("Error setting parameters", exc_info=True)

        # 5. Set the timeout return for the camera
        if not timeout:
            timeout = int(int(readout_time) + exptime_ms + 10000)
        else:
            timeout = 10000000

        # 6. Get the exposure start time to use for the naming convention
        start_time = datetime.datetime.utcnow()
        self.lastExposed = start_time
        logger.info("Starting %(camPrefix)s exposure",
                    {'camPrefix': self.camPrefix})
        try:
            data = self.opt.readNFrames(N=1, timeout=timeout)[0][0]
        except Exception as e:
            self.lastError = str(e)
            logger.error("Unable to get camera data", exc_info=True)
            return {'elaptime': -1*(time.time()-s),
                    'error': "Failed to gather data from camera",
                    'send_alert': True}

        logger.info("Readout completed")
        logger.debug("Took: %s", time.time() - s)

        if not save_as:
            start_exp_time = start_time.strftime("%Y%m%d_%H_%M_%S")
            # Now make sure the utdate directory exists
            if not os.path.exists(os.path.join(self.outputDir,
                                               start_exp_time[:8])):
                logger.info("Making directory: %s", os.path.join(self.outputDir,
                                                                 start_exp_time[:8]))

                os.mkdir(os.path.join(self.outputDir, start_exp_time[:8]))

            save_as = os.path.join(self.outputDir, start_exp_time[:8], self.camPrefix+start_exp_time+'.fits')

        try:
            datetimestr = start_time.isoformat()
            datestr, timestr = datetimestr.split('T')
            hdu = fits.PrimaryHDU(data, uint=False)
            hdu.scale('int16', bzero=32768)
            hdu.header.set("EXPTIME", float(exptime), "Exposure Time in seconds")
            hdu.header.set("ADCSPEED", readout, "Readout speed in MHz")
            hdu.header.set("TEMP", self.opt.getParameter("SensorTemperatureReading"),
                           "Detector temp in deg C")
            hdu.header.set("GAIN_SET", 2, "Gain mode")
            hdu.header.set("ADC", 1, "ADC Quality")
            hdu.header.set("MODEL", 22, "Instrument Mode Number")
            hdu.header.set("INTERFC", "USB", "Instrument Interface")
            hdu.header.set("SNSR_NM", "E2V 2048 x 2048 (CCD 42-40)(B)", "Sensor Name")
            hdu.header.set("SER_NO", self.serialNumber, "Serial Number")
            hdu.header.set("TELESCOP", self.telescope, "Telescope ID")
            hdu.header.set("GAIN", self.gain, "Gain")
            hdu.header.set("CAM_NAME", "%s Cam" % self.camPrefix.upper(), "Camera Name")
            hdu.header.set("INSTRUME", "SEDM-P60", "Camera Name")
            hdu.header.set("UTC", start_time.isoformat(), "UT-Shutter Open")
            hdu.header.set("END_SHUT", datetime.datetime.utcnow().isoformat(), "Shutter Close Time")
            hdu.header.set("OBSDATE", datestr, "UT Start Date")
            hdu.header.set("OBSTIME", timestr, "UT Start Time")
            hdu.header.set("CRPIX1", self.crpix1, "Center X pixel")
            hdu.header.set("CRPIX2", self.crpix2, "Center Y pixel")
            hdu.header.set("CDELT1", self.cdelt1, self.cdelt1_comment)
            hdu.header.set("CDELT2", self.cdelt2, self.cdelt2_comment)
            hdu.header.set("CTYPE1", self.ctype1)
            hdu.header.set("CTYPE2", self.ctype2)
            hdu.writeto(save_as, output_verify="fix", )
            logger.info("%s created", save_as)
            if self.send_to_remote:
                ret = self.transfer.send(save_as)
                if 'data' in ret:
                    save_as = ret['data']
            return {'elaptime': time.time()-s, 'data': save_as}
        except Exception as e:
            self.lastError = str(e)
            logger.error("Error writing data to disk", exc_info=True)
            return {'elaptime': -1*(time.time()-s),
                    'error': 'Error writing file to disk:' % str(e)}


if __name__ == "__main__":
    x = Controller(cam_prefix='ifu', output_dir='/home/rsw/images', send_to_remote=False)
    if x.initialize():
        print("Camera initialized")
    else:
        print("I need to handle this error")
        print(x.lastError)
    for i in range(1):
        #print(y.take_image(exptime=0, readout=2.0))
        print(x.take_image(exptime=0, readout=2))
    print("I made it here")
    time.sleep(10)
