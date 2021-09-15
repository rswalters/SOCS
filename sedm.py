from cameras.server import cam_client
from observatory.server import ocs_client
from sky.server import sky_client
from sanity.server import sanity_client
from utils import sedmHeader, rc_filter_coords
import os
import json
import datetime
import logging
from logging.handlers import TimedRotatingFileHandler
import time
from threading import Thread
import math
import pprint
import numpy as np
import shutil
import glob
import pandas as pd
import random
from twilio.rest import Client
from astropy.time import Time
import pickle

from utils.message_server import (message_handler, response_handler,
                                  error_handler)
from utils.sedmlogging import setup_logger
import yaml

# Open the config file
SR = os.path.abspath(os.path.dirname(__file__) + '/')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)

# Setup logger
name = "sedmLogger"
logfile = os.path.join(params['logging']['logpath'], 'sedm.log')
logger = setup_logger(name, log_file=logfile)


def make_alert_call():
    account_sid = ''
    auth_token = ''

    client = Client(account_sid, auth_token)

    call = client.calls.create(url='',
                               to='',
                               from_='')

    print(call.sid)


# noinspection PyPep8Naming,PyShadowingNames
class SEDm:
    def __init__(self, observer="SEDm", run_ifu=True, run_rc=True,
                 initialized=False, run_stage=True, run_arclamps=True,
                 run_ocs=True, run_telescope=True, run_sky=True,
                 run_sanity=True, configuration_file='', data_dir=None,
                 stop_file=None):
        """

        :param observer:
        :param run_ifu:
        :param run_rc:
        :param initialized:
        :param run_stage:
        :param run_arclamps:
        :param run_ocs:
        :param run_telescope:
        """
        logger.info("Robotic system initializing")
        self.observer = observer
        self.run_ifu = run_ifu
        self.run_rc = run_rc
        self.run_stage = run_stage
        self.run_ocs = run_ocs
        self.run_sky = run_sky
        self.run_sanity = run_sanity
        self.run_arclamps = run_arclamps
        self.run_telescope = run_telescope
        self.initialized = initialized
        self.data_dir = data_dir

        self.header = sedmHeader.addHeader()
        self.rc = None
        self.ifu = None
        self.ocs = None
        self.sky = None
        self.sanity = None
        self.lamp_dict_status = {'cd': 'off', 'hg': 'off', 'xe': 'off'}
        self.stage_dict = {'ifufocus': -999, 'ifufoc2': -999}
        self.get_tcs_info = True
        self.get_lamp_info = True
        self.get_stage_info = True
        self.p60prpi = 'SEDm'
        self.p60prnm = 'SEDmOBS'
        self.p60prid = '2019B-NoID'
        self.obj_id = -1
        self.req_id = -1
        self.guider_list = []
        self.lamp_wait_time = dict(xe=120, cd=420, hg=120, hal=120)
        self.calibration_id_dict = dict(bias=3, twilight=11, hal=5,
                                        hg=13, xe=12, cd=14)
        self.calibration_id_dict['focus'] = {'ifu': 10, 'rc': 6}
        self.telescope_moving_done_path = 'telescope_move_done.txt'
        self.required_sciobs_keywords = ['ra', 'dec', 'name', 'obs_dict']

        if not configuration_file:
            configuration_file = os.path.join(SR, 'config', 'sedm_config.yaml')

        with open(configuration_file) as data_file:
            self.params = yaml.load(data_file, Loader=yaml.FullLoader)

        self.base_image_dir = self.params['setup']['image_dir']
        self.stop_file = self.params['commands']['stop_file']
        self.stow_profiles = self.params['observatory']['tcs']['stow_profiles']
        self.ifu_ip = self.params['servers']['cameras']['ifu']['ip']
        self.ifu_port = self.params['servers']['cameras']['ifu']['port']
        self.rc_ip = self.params['servers']['cameras']['rc']['ip']
        self.rc_port = self.params['servers']['cameras']['rc']['port']
        self.non_sidereal_dir = self.params['setup']['non_sid_dir']
        self.directory_made = False
        self.obs_dir = ""
        self.verbose = False

    def _ut_dir_date(self, offset=0):
        dir_date = (datetime.datetime.utcnow() +
                    datetime.timedelta(days=offset))
        dir_date = dir_date.strftime("%Y%m%d")
        #logger.info("Setting directory date to: %s", dir_date)
        return dir_date

    def initialize(self):
        """
        Initialize the system based on the initial conditions set from
        calling SEDm class
        :return:
        """

        start = time.time()
        if self.run_rc:
            logger.info("Initializing RC camera on")
            self.rc = cam_client.Camera(self.rc_ip, self.rc_port)
            print(self.rc.initialize(), 'rc return')
        print(self.run_ifu, "IFU status return")
        if self.run_ifu:
            logger.info("Initializing IFU camera")
            self.ifu = cam_client.Camera(self.ifu_ip, self.ifu_port)
            print(self.ifu.initialize(), 'ifu return')
        if self.run_sky:
            logger.info("Initializing sky server")
            self.sky = sky_client.Sky()
        if self.run_ocs:
            logger.info("Initializing observatory components")
            self.ocs = ocs_client.Observatory()

            if self.run_arclamps and self.run_stage and self.run_telescope:
                print(self.ocs.initialize_ocs(), 'ocs_return')
                print(self.ocs.take_control())
            else:
                if self.run_arclamps:
                    self.ocs.initialize_lamps()
                if self.run_stage:
                    self.ocs.initialize_stages()
                if self.run_telescope:
                    self.ocs.initialize_tcs()
        if self.run_sanity:
            logger.info("Initializing sanity server")
            self.sanity = sanity_client.Sanity()
        self.initialized = True
        return {'elaptime': time.time() - start, 'data': "System initialized"}

    def get_status_dict(self, do_lamps=True, do_stages=True):
        stat_dict = {}

        ret = self.ocs.check_pos()
        if 'data' in ret:

            stat_dict.update(ret['data'])
        else:
            ret = self.ocs.check_pos()
            if 'data' in ret:
                stat_dict.update(ret['data'])
        try:
            stat_dict.update(self.ocs.check_weather()['data'])
            stat_dict.update(self.ocs.check_status()['data'])
        except Exception as e:
            print(str(e))
            pass
        if do_lamps:
            stat_dict['xe_lamp'] = self.ocs.arclamp('xe', 'status', force_check=True)['data']
            self.lamp_dict_status['xe'] = stat_dict['xe_lamp']
            stat_dict['cd_lamp'] = self.ocs.arclamp('cd', 'status', force_check=True)['data']
            self.lamp_dict_status['cd'] = stat_dict['cd_lamp']
            stat_dict['hg_lamp'] = self.ocs.arclamp('hg', 'status', force_check=True)['data']
            self.lamp_dict_status['hg'] = stat_dict['hg_lamp']
        else:
            stat_dict['xe_lamp'] = self.lamp_dict_status['xe']
            stat_dict['cd_lamp'] = self.lamp_dict_status['cd']
            stat_dict['hg_lamp'] = self.lamp_dict_status['hg']
        if do_stages:
            stat_dict['ifufocus'] = self.ocs.stage_position(1)['data']
            self.stage_dict['ifufocus'] = stat_dict['ifufocus']
            stat_dict['ifufoc2'] = self.ocs.stage_position(2)['data']
            self.stage_dict['ifufoc2'] = stat_dict['ifufoc2']
        else:
            stat_dict['ifufocus'] = self.stage_dict['ifufocus']
            stat_dict['ifufoc2'] = self.stage_dict['ifufoc2']
        return stat_dict

    def take_image(self, cam, exptime=0, shutter='normal', readout=2.0,
                   start=None, save_as='', test='', imgtype='NA', objtype='NA',
                   object_ra="", object_dec="", email='', p60prid='NA',
                   p60prpi='SEDm', p60prnm='', obj_id=-999, req_id=-999,
                   objfilter='NA', imgset='NA', is_rc=False, abpair=False,
                   name='Unknown', run_background_command=True, do_lamps=True,
                   do_stages=True, verbose=False,
                   background_command="next_target"):
        """

        :param do_stages:
        :param do_lamps:
        :type object_ra: object
        :param run_background_command:
        :param background_command:
        :param exptime:
        :param cam:
        :param shutter:
        :param readout:
        :param name:
        :param start:
        :param save_as:
        :param test:
        :param imgtype:
        :param objtype:
        :param object_ra:
        :param object_dec:
        :param email:
        :param p60prid:
        :param p60prpi:
        :param p60prnm:
        :param obj_id:
        :param req_id:
        :param objfilter:
        :param imgset:
        :param is_rc:
        :param abpair:
        :return:
        """
        # Timekeeping
        if not start:
            start = time.time()
        # logger.info("Preparing to take an image")
        # Make sure the image directory exists on local host
        if not save_as:
            if not self.directory_made:
                self.obs_dir = os.path.join(self.base_image_dir,
                                            self._ut_dir_date())
                if not os.path.exists(os.path.join(self.base_image_dir,
                                                   self._ut_dir_date())):
                    os.mkdir(os.path.join(self.base_image_dir,
                                          self._ut_dir_date()))
                    self.directory_made = True
        obsdict = {'starttime': start}

        readout_end = (datetime.datetime.utcnow()
                       + datetime.timedelta(seconds=exptime))

        # 1. Start the exposure and return back to the prompt
        ret = cam.take_image(shutter=shutter, exptime=exptime,
                             readout=readout, save_as=save_as,

                             return_before_done=True)

        if verbose:
            print(ret)

        # print(ret)
        # 2. Get the TCS information for the conditions at the start of the
        # exposure
        obsdict.update(self.get_status_dict(do_stages=do_stages, do_lamps=do_lamps))
        if not object_ra or not object_dec:
            print("Using TCS RA and DEC")
            object_ra = obsdict['telescope_ra']
            object_dec = obsdict['telescope_dec']

        obsdict.update(self.header.set_project_keywords(test=test,
                                                        imgtype=imgtype,
                                                        objtype=objtype,
                                                        object_ra=object_ra,
                                                        object_dec=object_dec,
                                                        email=email, name=name,
                                                        p60prid=p60prid,
                                                        p60prpi=p60prpi,
                                                        p60prnm=p60prnm,
                                                        obj_id=obj_id,
                                                        req_id=req_id,
                                                        objfilter=objfilter,
                                                        imgset=imgset,
                                                        is_rc=is_rc,
                                                        abpair=abpair))

        while datetime.datetime.utcnow() < readout_end:
            time.sleep(.01)

        end_dict = self.get_status_dict(do_lamps=False, do_stages=False)
        obsdict.update(self.header.prep_end_header(end_dict))

        if run_background_command:
            self.run_background_command(background_command)

        # print("Reconnecting now")
        try:
            ret = cam.listen()
        except Exception as e:
            logger.error("unable to listen for new image", exc_info=True)
            print("Error waiting for the file to write out")
            ret = None
            pass

        if isinstance(ret, dict) and 'data' in ret:
            #print("Adding the header")
            self.header.set_header(ret['data'], obsdict)
            return ret
        else:
            print(ret, "There was no return")

            # This is a test to see if last image failed to write or the connection
            # timed out.
            list_of_files = glob.glob('/home/sedm/images/%s/*.fits' % datetime.datetime.utcnow().strftime(
                "%Y%m%d"))  # * means all if need specific format then *.csv
            latest_file = max(list_of_files, key=os.path.getctime)

            print(latest_file)
            base_file = os.path.basename(latest_file)
            if 'ifu' in base_file:
                fdate = datetime.datetime.strptime(base_file,
                                                   "ifu%Y%m%d_%H_%M_%S.fits")
            else:
                fdate = datetime.datetime.strptime(base_file,
                                                   "rc%Y%m%d_%H_%M_%S.fits")

            start_time = readout_end - datetime.timedelta(seconds=exptime)
            fdate += datetime.timedelta(seconds=1)
            diff = (fdate - start_time).seconds

            # Re-establish the camera connection just to make sure the
            # issue isn't with them
            print(self.initialize())

            if diff < 10:
                print("Add the header")
                print(self.header.set_header(latest_file, obsdict))
                return {'elaptime': time.time()-start, 'data': latest_file}
            else:
                make_alert_call()
                print("File not a match saving header info")
                save_path = os.path.join(self.obs_dir,
                                         "header_dict_"
                                         +start_time.strftime("%Y%m%d_%H_%M_%S"))
                f = open(save_path, "wb")
                pickle.dump(dict, f)
                f.close()
                return {
                    "elaptime": time.time()-start,
                    "error": "Camera not returned",
                    "data": "header file saved to %s" % save_path
                }

    def run_background_command(self, command):
        """

        :param command:
        :return:
        """
        start = time.time()

        if os.path.exists(self.stop_file):
            return {'elaptime': time.time() - start, 'error': 'Stop file in place'}

        if command.lower() == "move_to_next_target":
            pass

    def take_bias(self, cam, N=1, startN=1, shutter='closed', readout=2.0,
                  generate_request_id=True, name='', save_as='', test='',
                  req_id=-999):
        """

        :param req_id:
        :param readout:
        :param cam:
        :param test:
        :param save_as:
        :param N:
        :param shutter:
        :param startN:
        :param generate_request_id:
        :param name:
        :return:
        """
        # Pause condition to keep the IFU and RC cameras out of sync
        # during calibrations.  Does not effect the efficiency of the
        # system as a whole
        time.sleep(2)

        img_list = []
        start = time.time()

        if not name:
            name = 'bias'

        obj_id = self.calibration_id_dict['bias']

        if generate_request_id:
            ret = self.sky.get_calib_request_id(camera=cam.prefix()['data'],
                                                N=N, exptime=0,
                                                object_id=obj_id)
            if "data" in ret:
                req_id = ret['data']

        for img in range(startN, N + 1, 1):
            print(N, startN)
            if N != startN:
                start = time.time()
                do_stages = False
                do_lamps = False
            else:
                do_stages = True
                do_lamps = True
            namestr = "%s %s of %s" % (name, img, N)
            ret = self.take_image(cam, shutter=shutter, readout=readout,
                                  name=namestr, start=start, test=test,
                                  save_as=save_as, imgtype='bias',
                                  objtype='Calibration', exptime=0,
                                  object_ra="", object_dec="", email='',
                                  p60prid='2018A-calib', p60prpi='SEDm',
                                  p60prnm='SEDm Calibration File',
                                  obj_id=obj_id, req_id=req_id,
                                  objfilter='NA', imgset='NA',
                                  do_stages=do_stages, do_lamps=do_lamps,
                                  is_rc=False, abpair=False)

            if 'data' in ret:
                img_list.append(ret['data'])

        if generate_request_id:
            self.sky.update_target_request(req_id, status="COMPLETED")
            # TODO Parse the return here

        return {'elaptime': time.time() - start, 'data': img_list}

    def take_dome(self, cam, N=1, exptime=180, readout=2.0,
                  do_lamp=True, wait=True, obj_id=None,
                  shutter='normal', name='', test='',
                  move=False, ha=3.6, dec=50, domeaz=40,
                  save_as=None, req_id=-999,
                  startN=1, generate_request_id=True):
        """

        :param cam:
        :param N:
        :param exptime:
        :param readout:
        :param do_lamp:
        :param wait:
        :param obj_id:
        :param shutter:
        :param name:
        :param test:
        :param move:
        :param ha:
        :param dec:
        :param domeaz:
        :param save_as:
        :param req_id:
        :param startN:
        :param generate_request_id:
        :return:
        """
        time.sleep(2)
        start = time.time()  # Start the clock on the observation
        # 1. Check if the image type is calibration type and set the tracking
        #    list if so
        if not obj_id:
            obj_id = self.calibration_id_dict['hal']

        if generate_request_id:
            ret = self.sky.get_calib_request_id(camera=cam.prefix()['data'],
                                                N=N, exptime=0,
                                                object_id=obj_id)

            if "data" in ret:
                req_id = ret['data']
        # 2. Move the telescope to the calibration stow position
        if move:
            ret = self.ocs.stow(ha=ha, dec=dec, domeaz=domeaz)
            print(ret)
            # 3a. Check that we made it to the calibration stow position
            # TODO: Implement return checking of OCS returns
            # if not ret:
            #    return "Unable to move telescope to stow position"

        # 3. Turn on the lamps and wait for them to stabilize
        if do_lamp:
            ret = self.ocs.halogens_on()
            print(ret)

        if wait:
            print("Waiting %s seconds for dome lamps to warm up" %
                  self.lamp_wait_time['hal'])
            time.sleep(self.lamp_wait_time['hal'])

        if not name:
            name = 'dome lamp'

        # 4. Start the observations
        for img in range(startN, N + 1, 1):

            # 5a. Set the image header keyword name
            print(N, startN)
            if N != startN:
                start = time.time()
                do_stages = False
                do_lamps = False
            else:
                do_stages = True
                do_lamps = True

            namestr = "%s %s of %s" % (name, img, N)
            ret = self.take_image(cam, shutter=shutter, readout=readout,
                                  name=namestr, start=start, test=test,
                                  save_as=save_as, imgtype='dome',
                                  objtype='Calibration', exptime=exptime,
                                  object_ra="", object_dec="", email='',
                                  p60prid='2018A-calib', p60prpi='SEDm',
                                  p60prnm='SEDm Calibration File',
                                  obj_id=obj_id, req_id=req_id,
                                  objfilter='NA', imgset='NA',
                                  do_lamps=do_lamps, do_stages=do_stages,
                                  is_rc=False, abpair=False)
            print(ret)

        if do_lamp:
            self.ocs.halogens_off()

        if generate_request_id:
            self.sky.update_target_request(req_id, status="COMPLETED")

    def take_arclamp(self, cam, lamp, N=1, exptime=1, readout=2.0,
                     do_lamp=True, wait=True, obj_id=None,
                     shutter='normal', name='', test='',
                     ha=3.6, dec=50.0, domeaz=40,
                     move=True, save_as=None, req_id=-999,
                     startN=1, generate_request_id=True):
        """

        :param cam:
        :param lamp:
        :param N:
        :param exptime:
        :param readout:
        :param do_lamp:
        :param wait:
        :param obj_id:
        :param shutter:
        :param name:
        :param test:
        :param ha:
        :param dec:
        :param domeaz:
        :param move:
        :param save_as:
        :param req_id:
        :param startN:
        :param generate_request_id:
        :return:
        """

        start = time.time()  # Start the clock on the observation

        # Hack to get the naming convention exactly right for the pipeline
        if not name:
            name = lamp[0].upper() + lamp[-1].lower()

        # 1. Check if the image type is calibration type and set the tracking
        #    list if so
        if not obj_id:
            obj_id = self.calibration_id_dict[lamp.lower()]

        if generate_request_id:
            ret = self.sky.get_calib_request_id(camera=cam.prefix()['data'],
                                                N=N, exptime=0,
                                                object_id=obj_id)

            if "data" in ret:
                req_id = ret['data']

        # 2. Move the telescope to the calibration stow position
        if move:
            ret = self.ocs.stow(ha=ha, dec=dec, domeaz=domeaz)
            print(ret)
            # 3a. Check that we made it to the calibration stow position
            # TODO: Implement return checking of OCS returns
            # if not ret:
            #    return "Unable to move telescope to stow position"

        # 3. Turn on the lamps and wait for them to stabilize
        if do_lamp:
            ret = self.ocs.arclamp(lamp, command="ON")
            print(ret)
        if wait:
            print("Waiting %s seconds for %s lamp to warm up" %
                  (lamp, self.lamp_wait_time[lamp.lower()]))
            time.sleep(self.lamp_wait_time[lamp.lower()])

        if not name:
            name = lamp

        # 4. Start the observations
        for img in range(startN, N + 1, 1):

            # 5a. Set the image header keyword name
            if N != startN:
                start = time.time()

            namestr = "%s %s of %s" % (name, img, N)
            ret = self.take_image(cam, shutter=shutter, readout=readout,
                                  name=namestr, start=start, test=test,
                                  save_as=save_as, imgtype='lamp',
                                  objtype='Calibration', exptime=exptime,
                                  object_ra="", object_dec="", email='',
                                  p60prid='2018A-calib', p60prpi='SEDm',
                                  p60prnm='SEDm Calibration File',
                                  obj_id=obj_id, req_id=req_id,
                                  objfilter='NA', imgset='NA',
                                  is_rc=False, abpair=False)
            print(ret)

        if do_lamp:
            self.ocs.arclamp(lamp, command="OFF")

        if generate_request_id:
            self.sky.update_target_request(req_id, status="COMPLETED")

    def take_twilight(self, cam, N=1, exptime=30, readout=0.1,
                      do_lamp=True, wait=True, obj_id=None,
                      shutter='normal', name='', test='',
                      ra=3.6, dec=50.0, end_time=None,
                      get_focus_coords=True, use_sun_angle=True,
                      max_angle=-11, min_angle=-5, max_time=100,
                      move=True, save_as=None, req_id=-999,
                      startN=1, generate_request_id=True):
        """

        :param cam:
        :param lamp:
        :param N:
        :param exptime:
        :param readout:
        :param do_lamp:
        :param wait:
        :param obj_id:
        :param shutter:
        :param name:
        :param test:
        :param ha:
        :param dec:
        :param domeaz:
        :param move:
        :param save_as:
        :param req_id:
        :param startN:
        :param generate_request_id:
        :return:
        """

        start = time.time()  # Start the clock on the observation

        # Hack to get the naming convention exactly right for the pipeline
        if not name:
            name = "Twilight"

        # 1. Check if the image type is calibration type and set the tracking
        #    list if so
        if not obj_id:
            obj_id = self.calibration_id_dict["twilight"]

        if generate_request_id:
            ret = self.sky.get_calib_request_id(camera=cam.prefix()['data'],
                                                N=N, exptime=0,
                                                object_id=obj_id)

            if "data" in ret:
                req_id = ret['data']

        # 2. Move the telescope to the calibration stow position
        if move:
            stat = self.ocs.check_status()

            if 'data' in stat:
                ret = stat['data']['dome_shutter_status']
                if 'closed' in ret.lower():
                    print("Opening dome")
                    print(self.ocs.dome("open"))
                else:
                    print("Dome open skipping")

            if get_focus_coords:
                ret = self.sky.get_focus_coords()
                print(ret, 'coords')
                if 'data' in ret:
                    ra = ret['data']['ra']
                    dec = ret['data']['dec']

            ret = self.ocs.tel_move(name=name, ra=ra,
                                    dec=dec)

            if 'data' not in ret:
                print(ret)
                pass

        n = 1
        # 4. Start the observations
        while time.time() - start < max_time:
            if use_sun_angle:
                ret = self.sky.get_twilight_exptime()

                print(ret)
                if 'data' in ret:
                    exptime = ret['data']['exptime']

                if n != 1:
                    start = time.time()
                    do_stages = False
                    do_lamps = False
                else:
                    do_stages = True
                    do_lamps = True

                namestr = name + ' ' + str(N)
                if end_time:
                    ctime = datetime.datetime.utcnow()
                    etime = ctime + datetime.timedelta(seconds=exptime+50)
                    if Time(etime) > end_time:
                        break
                ret = self.take_image(cam, shutter=shutter, readout=readout,
                                      name=namestr, start=start, test=test,
                                      save_as=save_as, imgtype='twilight',
                                      objtype='Calibration', exptime=exptime,
                                      object_ra="", object_dec="", email='',
                                      p60prid='2018A-calib', p60prpi='SEDm',
                                      p60prnm='SEDm Calibration File',
                                      obj_id=obj_id, req_id=req_id, do_stages=do_stages,
                                      do_lamps=do_lamps,
                                      objfilter='NA', imgset='NA',
                                      is_rc=False, abpair=False)
                if move:
                    off = random.random()
                    if off >= .5:
                        sign = -1
                    else:
                        sign = 1

                    ra_off = sign * off * 20
                    dec_off = sign * off * 20

                    self.ocs.tel_offset(0, -15)


                    self.ocs.tel_offset()
                n += 1
                print(ret)

        if generate_request_id:
            self.sky.update_target_request(req_id, status="COMPLETED")

    def take_datacube(self, cam, cube='ifu', check_for_previous=True,
                      custom_file='', move=False, ha=None, dec=None,
                      domeaz=None):
        """

        :param move:
        :param ha:
        :param dec:
        :param domeaz:
        :param check_for_previous:
        :param custom_file:
        :param cam:
        :param cube:
        :return:
        """
        start = time.time()
        if custom_file:
            with open(custom_file) as data_file:
                cube_params = json.load(data_file)
        else:
            cube_params = self.params

        cube_type = "%s_datacube" % cube
        print(cube_params)
        print(cube_type)
        data_dir = os.path.join(self.base_image_dir,
                                self._ut_dir_date())

        if move:
            if not ha:
                ha = self.stow_profiles['calibrations']['ha']
            if not dec:
                dec = self.stow_profiles['calibrations']['dec']
            if not domeaz:
                domeaz = self.stow_profiles['calibrations']['domeaz']

            self.ocs.stow(ha=ha, dec=dec, domeaz=domeaz)

        if 'fast_bias' in cube_params[cube_type]['order']:
            N = cube_params[cube_type]['fast_bias']['N']
            files_completed = 0
            if check_for_previous:
                ret = self.sanity.check_for_files(camera=cube,
                                                  keywords={'object': 'bias',
                                                            'adcspeed': 2.0},
                                                  data_dir=data_dir)
                if 'data' in ret:
                    files_completed = len(ret['data'])

            if files_completed >= N:
                print("Fast biases already done")
                pass
            elif files_completed < N:
                N = N - files_completed
                self.take_bias(cam, N=N,
                               readout=2.0)

        if 'slow_bias' in cube_params[cube_type]['order']:
            N = cube_params[cube_type]['slow_bias']['N']
            files_completed = 0
            if check_for_previous:
                ret = self.sanity.check_for_files(camera=cube,
                                                  keywords={'object': 'bias',
                                                            'adcspeed': 0.1},
                                                  data_dir=data_dir)
                if 'data' in ret:
                    files_completed = len(ret['data'])

            if files_completed >= N:
                print("Slow biases already done")
                pass
            elif files_completed < N:
                N = N - files_completed
                self.take_bias(cam, N=N,
                               readout=0.1)

        if 'dome' in cube_params[cube_type]['order']:
            N = cube_params[cube_type]['dome']['N']
            files_completed = 0
            check_for_previous = False
            if check_for_previous:
                ret = self.sanity.check_for_files(camera=cube,
                                                  keywords={'object': 'dome',
                                                            'adcspeed': 2.0},
                                                  data_dir=data_dir)
                if 'data' in ret:
                    files_completed = len(ret['data'])

            if files_completed >= N:
                pass
            elif files_completed < N:
                N = N - files_completed
                print("Turning on Halogens")
                ret = self.ocs.halogens_on()
                print(ret)
                time.sleep(120)
                for i in cube_params[cube_type]['dome']['readout']:
                    print(i)
                    for j in cube_params[cube_type]['dome']['exptime']:
                        print(j)
                        self.take_dome(cam, N=N, readout=i, do_lamp=False,
                                       wait=False, exptime=j, move=False)
                print("Turning off Halogens")
                ret = self.ocs.halogens_off()
                print(ret)

        for lamp in ['hg', 'xe', 'cd']:
            if lamp in cube_params[cube_type]['order']:
                N = cube_params[cube_type][lamp]['N']
                if check_for_previous:
                    pass
                exptime = cube_params[cube_type][lamp]['exptime']
                self.take_arclamp(cam, lamp, N=N, readout=2.0, move=False,
                                  exptime=exptime)
        return {'elaptime': time.time() - start, 'data': '%s complete' %
                                                         cube_type}

    def take_datacube_eff(self, custom_file='', move=False,
                          ha=None, dec=None, domeaz=None):
        """

        :param move:
        :param ha:
        :param dec:
        :param domeaz:
        :param custom_file:
        :return:
        """
        start = time.time()

        skip_next = False

        if not self.run_rc and not self.run_ifu:
            print("Both cameras have to active")
            return {'elaptime': time.time() - start,
                    'error': 'Efficiency cube mode can only '
                             'be run with both cameras active'}

        if custom_file:
            with open(custom_file) as data_file:
                cube_params = json.load(data_file)
        else:
            cube_params = self.params

        print(cube_params)

        if move:
            if not ha:
                ha = self.stow_profiles['calibrations']['ha']
            if not dec:
                dec = self.stow_profiles['calibrations']['dec']
            if not domeaz:
                domeaz = self.stow_profiles['calibrations']['domeaz']

            self.ocs.stow(ha=ha, dec=dec, domeaz=domeaz)

        # Start by turning on the Cd lamp:
        print("Turning on Cd Lamp")
        ret = self.ocs.arclamp('cd', command="ON")
        print(ret, "CD ON")
        ret = self.ocs.arclamp('cd', 'status', force_check=True)['data']

        if 'on' not in ret:
            skip_next = True

        lamp_start = time.time()

        # Now take the biases while waiting for things to finish

        # Start the RC biases in the background
        N_rc = cube_params['rc']['fast_bias']['N']
        t = Thread(target=self.take_bias, kwargs={'cam': self.rc,
                                                  'N': N_rc,
                                                  'readout': 2.0,
                                                  })
        t.daemon = True
        t.start()

        # Wait 5s to start the IFU calibrations so they finish last
        time.sleep(5)
        N_ifu = cube_params['ifu']['fast_bias']['N']
        self.take_bias(self.ifu, N=N_ifu, readout=2.0)

        # Start the RC biases in the background
        N_rc = cube_params['rc']['fast_bias']['N']
        t = Thread(target=self.take_bias, kwargs={'cam': self.rc,
                                                  'N': N_rc,
                                                  'readout': .1,
                                                  })
        t.daemon = True
        t.start()

        # Wait 5s to start the IFU calibrations so they finish last
        time.sleep(5)
        N_ifu = cube_params['ifu']['fast_bias']['N']
        self.take_bias(self.ifu, N=N_ifu, readout=.1)

        # Make sure that we have waited long enough for the 'Cd' lamp to warm
        while time.time() - lamp_start < self.lamp_wait_time['cd']:
            time.sleep(5)

        # Start the 'cd' lamps
        if not skip_next:
            N_cd = cube_params['ifu']['cd']['N']
            exptime = cube_params['ifu']['cd']['exptime']
            self.take_arclamp(self.ifu, 'cd', wait=False, do_lamp=False, N=N_cd,
                              readout=2.0, move=False, exptime=exptime)

            # Turn the lamps off
            ret = self.ocs.arclamp('cd', command="OFF")

            print(ret, "CD OFF")
        else:
            ret = self.ocs.arclamp('cd', command="OFF")
            skip_next = False

        # Move onto to the dome lamp
        print("Turning on Halogens")
        ret = self.ocs.halogens_on()
        print(ret)
        # time.sleep(120)
        if 'data' in ret:
            # Start the IFU dome lamps in the background
            N_ifu = cube_params['ifu']['dome']['N']
            t = Thread(target=self.take_dome, kwargs={'cam': self.ifu,
                                                      'N': 5,
                                                      'exptime': 180,
                                                      'readout': 2.0,
                                                      'wait': False,
                                                      'do_lamp': False
                                                      })
            t.daemon = True
            t.start()

            # Now start the RC dome lamps
            time.sleep(5)
            N_rc = cube_params['rc']['dome']['N']
            for i in cube_params['rc']['dome']['readout']:
                print(i)
                for j in cube_params['rc']['dome']['exptime']:
                    print(j)
                    self.take_dome(self.rc, N=5, readout=i, do_lamp=False,
                                   wait=False, exptime=j, move=False)
            print("Turning off Halogens")
            ret = self.ocs.halogens_off()
            print(ret)
        else:
            make_alert_call()

        print("Starting other Lamps")
        for lamp in ['hg', 'xe']:
            if lamp in cube_params['ifu']['order']:
                N = cube_params['ifu'][lamp]['N']
                exptime = cube_params['ifu'][lamp]['exptime']
                self.take_arclamp(self.ifu, lamp, N=N, readout=2.0, move=False,
                                  exptime=exptime)

        return {'elaptime': time.time() - start,
                'data': 'Efficiency cube complete'}

    def prepare_next_observation(self, exptime=100, target_list=None,
                                 obsdatetime=None,
                                 airmass=(1, 2.5), moon_sep=(20, 180),
                                 altitude_min=15, ha=(18.75, 5.75),
                                 return_type='json',
                                 do_sort=True,
                                 sort_columns=('priority', 'start_alt'),
                                 sort_order=(False, False), save=True,
                                 save_as='', move=True,
                                 check_end_of_night=True, update_coords=True):
        """

        :param exptime:
        :param target_list:
        :param obsdatetime:
        :param airmass:
        :param moon_sep:
        :param altitude_min:
        :param ha:
        :param return_type:
        :param do_sort:
        :param sort_columns:
        :param sort_order:
        :param save:
        :param save_as:
        :param move:
        :param check_end_of_night:
        :param update_coords:
        :return:
        """
        if not obsdatetime:
            obsdatetime = datetime.datetime.utcnow() + datetime.timedelta(seconds=exptime)

        if os.path.exists(self.telescope_moving_done_path):
            os.remove(self.telescope_moving_done_path)

        # Here we wait until readout starts
        while datetime.datetime.utcnow() < obsdatetime:
            time.sleep(1)

        print("Getting next target")
        ret = self.sky.get_next_observable_target(target_list=target_list,
                                                  obsdatetime=obsdatetime.isoformat(),
                                                  airmass=airmass,
                                                  moon_sep=moon_sep,
                                                  altitude_min=altitude_min,
                                                  ha=ha, do_sort=do_sort,
                                                  return_type=return_type,
                                                  sort_order=sort_order,
                                                  sort_columns=sort_columns,
                                                  save=save, save_as=save_as,
                                                  check_end_of_night=check_end_of_night,
                                                  update_coords=update_coords)
        print(ret)

        if "data" in ret:
            pprint.pprint(ret['data'])

            if move:
                self.ocs.tel_move(ra=ret['data']['ra'],
                                  dec=ret['data']['dec'])

    def run_focus_seq(self, cam, focus_type, exptime=10, foc_range=None,
                      solve=True, get_request_id=True, run_acquisition=True,
                      get_focus_coords=True, focus_coords=None,
                      shutter="normal", readout=2, name="",
                      test="", save_as="", imgtype='Focus',
                      ra=0, dec=0, equinox=2000, do_lamp=False,
                      epoch="", ra_rate=0, dec_rate=0, motion_flag="",
                      p60prid='2018A-calib', p60prpi='SEDm',
                      email='rsw@astro.caltech.edu', wait=True,
                      p60prnm='SEDm Calibration File', obj_id=-999,
                      objfilter='ifu', imgset='A', is_rc=False,
                      req_id=-999, acq_readout=2.0, lamp='xe',
                      offset_to_ifu=True, objtype='Focus',
                      non_sid_targ=False, guide_readout=2.0,
                      move_during_readout=True, abpair=False,
                      move=True, mark_status=True, status_file=''
                      ):
        start = time.time()  # Start the clock on the observation
        img_list = []
        error_list = []

        if get_focus_coords:
            ret = self.sky.get_focus_coords()
            print(ret, 'coords')
            if 'data' in ret:
                ra = ret['data']['ra']
                dec = ret['data']['dec']
                ret = self.ocs.tel_move(name=name, ra=ra,
                                        dec=dec)

                if 'data' not in ret:
                    pass

        obj_id = self.calibration_id_dict['focus'][cam.prefix()['data']]
        if get_request_id:
            ret = self.sky.get_calib_request_id(camera=cam.prefix()['data'],
                                                N=1, exptime=0,
                                                object_id=obj_id)
            if "data" in ret:
                req_id = ret['data']

        if move and focus_type == 'ifu_stage':
            ret = self.ocs.stow(**self.stow_profiles['calibrations'])

            if 'data' not in ret:
                pass
        elif move and focus_type == 'rc_focus':
            self.ocs.tel_move(name=name, ra=ra, dec=dec, equinox=equinox,
                              ra_rate=ra_rate, dec_rate=dec_rate,
                              motion_flag=motion_flag, epoch=epoch)

        elif move and focus_type == 'ifu_focus':
            if get_focus_coords:
                ret = self.sky.get_focus_coords()

                if 'data' in ret:
                    ra = ret['data']['ra']
                    dec = ret['data']['dec']
                    ret = self.ocs.tel_move(name=name, ra=ra,
                                            dec=dec)

                    if 'data' not in ret:
                        pass
            else:
                self.ocs.tel_move(name=name, ra=ra, dec=dec, equinox=equinox,
                                  ra_rate=ra_rate, dec_rate=dec_rate,
                                  motion_flag=motion_flag, epoch=epoch)

        if do_lamp:
            ret = self.ocs.arclamp(lamp, command="ON")
            print(ret)

            if wait:
                print("Waiting %s seconds for dome lamps to warm up" %
                      self.lamp_wait_time[lamp.lower()])
                time.sleep(self.lamp_wait_time[lamp.lower()])

        if foc_range is None:
            if focus_type == 'ifu_stage':
                foc_range = np.arange(.1, .8, .1)
            elif focus_type == 'rc_focus' or focus_type == 'ifu_focus':
                foc_range = np.arange(16.25, 17.05, .05)
            elif focus_type == 'ifu_stage2':
                foc_range = np.arange(2, 3.6, .2)
            else:
                return -1 * (time.time() - start), "Unknown focus type"

        startN = 1
        N = 1
        for pos in foc_range:

            # 5a. Set the image header keyword name
            print(N, startN)
            if N != startN:
                start = time.time()
                do_stages = False
                do_lamps = False
            else:
                do_stages = True
                do_lamps = True

            N += 1
            print("%s-Moving to focus position: %fmm" % (focus_type, pos))

            if focus_type == 'ifu_stage':
                print("IFUSTAGE 1")
                self.ocs.move_stage(position=pos, stage_id=1)
            elif focus_type == 'rc_focus' or focus_type == 'ifu_focus':
                print("TELESCOPE SECONADRY")
                if move:
                    self.ocs.goto_focus(pos=pos)
            elif focus_type == 'ifu_stage2':
                print("IFUSTAGE2")
                self.ocs.move_stage(position=pos, stage_id=2)

            ret = self.take_image(cam, exptime=exptime,
                                  shutter=shutter, readout=readout,
                                  start=start, save_as=save_as, test=test,
                                  imgtype=imgtype, objtype=objtype,
                                  object_ra=ra, object_dec=dec,
                                  email=email, p60prid=p60prid, p60prpi=p60prpi,
                                  p60prnm=p60prnm, obj_id=obj_id,
                                  req_id=req_id, objfilter=objfilter,
                                  imgset=imgset, do_lamps=do_lamps,
                                  do_stages=do_stages,
                                  is_rc=is_rc, abpair=abpair, name=name)

            if 'data' in ret:
                img_list.append(ret['data'])

        if do_lamp:
            ret = self.ocs.arclamp(lamp, command="OFF")
            print(ret)

        logger.debug("Finished RC focus sequence")
        print(img_list)
        if solve:
            ret = self.sky.get_focus(img_list)
            print(ret)
            best_foc = False
            if 'data' in ret:
                best_foc = round(ret['data'][0], 2)
            if best_foc:
                print("Best FOCUS is:", best_foc)
                if focus_type == 'ifu_stage':
                    print("IFUSTAGE 1")
                    self.ocs.move_stage(position=best_foc, stage_id=1)
                elif focus_type == 'rc_focus' or focus_type == 'ifu_focus':
                    print("TELESCOPE SECONADRY")
                    self.ocs.goto_focus(pos=best_foc)
                elif focus_type == 'ifu_stage2':
                    print("IFUSTAGE2")
                    self.ocs.move_stage(position=best_foc, stage_id=2)
            else:
                print("Unable to calculate focus")
        return time.time() - start, img_list

    def run_guider_seq(self, cam, guide_length=0, readout=2.0,
                       shutter='normal', guide_exptime=1, email="",
                       objfilter="", req_id=-999, obj_id=-999,
                       object_ra="", object_dec="", test="",
                       is_rc=True, p60prpi="", p60prid="", do_corrections=True,
                       p60prnm="", name="", save_as="", imgset=""):

        start = time.time()
        time.sleep(2)

        end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=guide_length - 5)

        if readout == 2.0:
            readout_time = 7
        else:
            readout_time = 47

        self.guider_list = []
        if do_corrections:
            self.sky.start_guider(start_time=None, end_time=None,
                                  exptime=guide_length,
                                  image_prefix="rc", max_move=None,
                                  min_move=None,
                                  data_dir=os.path.join(self.base_image_dir,
                                                        self._ut_dir_date()),
                                  debug=False, wait_time=5)

        guide_done = (datetime.datetime.utcnow() +
                      datetime.timedelta(seconds=guide_exptime + readout_time))

        N = 1
        while guide_done <= end_time:
            if N == 1:
                do_stages = True
                do_lamps = True
            else:
                do_stages = False
                do_lamps = False
            N += 1
            try:
                ret = self.take_image(cam, exptime=guide_exptime,
                                      shutter=shutter, readout=readout,
                                      start=None, save_as=save_as, test=test,
                                      imgtype="Guider", objtype="Guider",
                                      object_ra=object_ra, object_dec=object_dec,
                                      email=email, p60prid=p60prid, p60prpi=p60prpi,
                                      p60prnm=p60prnm, obj_id=obj_id, imgset=imgset,
                                      req_id=req_id, objfilter=objfilter,
                                      do_stages=do_stages, do_lamps=do_lamps,
                                      is_rc=is_rc, abpair=False, name=name)
            except Exception as e:
                logger.error("Error taking guider image", exc_info=True)

            if 'data' in ret:
                self.guider_list.append(ret['data'])
            guide_done = (datetime.datetime.utcnow() +
                          datetime.timedelta(seconds=guide_exptime + readout_time))

        print(datetime.datetime.utcnow(), "Guider Done")
        print(time.time() - start, self.guider_list)

        while datetime.datetime.utcnow() < end_time:
            time.sleep(.5)

        if do_corrections:
            try:
                ret = self.sky.listen()
                print(ret, "SKY LISTEN")
            except Exception as e:
                print(str(e))
                logger.error("Error getting guider return", exc_info=True)

        logger.info("Gudier_list:%s" % self.guider_list)
        logger.debug("Finished guider sequence for %s" % name)

    def run_standard_seq(self, cam, shutter="normal",
                         readout=.1, name="", get_standard=True,
                         test="", save_as="", imgtype='Standard',
                         exptime=90, ra=0, dec=0, equinox=2000,
                         epoch="", ra_rate=0, dec_rate=0, motion_flag="",
                         p60prid='2018A-calib', p60prpi='SEDm', email='rsw@astro.caltech.edu',
                         p60prnm='SEDm Calibration File', obj_id=-999,
                         objfilter='ifu', imgset='A', is_rc=False,
                         run_acquisition=True, req_id=-999, acq_readout=2.0,
                         offset_to_ifu=True, objtype='Standard',
                         non_sid_targ=False, guide_readout=2.0,
                         move_during_readout=True, abpair=False,
                         guide=True, guide_shutter='normal', move=True,
                         guide_exptime=10, guide_save_as=None,
                         retry_on_failed_astrometry=False,
                         mark_status=True, status_file=''):
        start = time.time()

        if get_standard:
            ret = self.sky.get_standard()
            print(ret)

            if 'data' in ret:
                name = ret['data']['name']
                ra = ret['data']['ra']
                dec = ret['data']['dec']
                exptime = ret['data']['exptime']

        if move:
            if run_acquisition:
                ret = self.run_acquisition_seq(self.rc, ra=ra, dec=dec,
                                               equinox=equinox, ra_rate=ra_rate,
                                               dec_rate=dec_rate, motion_flag=motion_flag,
                                               exptime=30, readout=acq_readout,
                                               shutter=shutter, move=move, name=name,
                                               obj_id=obj_id, req_id=req_id,
                                               retry_on_failed_astrometry=retry_on_failed_astrometry,
                                               tcsx=False, test=test,
                                               p60prid=p60prid, p60prnm=p60prnm,
                                               p60prpi=p60prpi, email=email,
                                               retry_on_sao_on_failed_astrometry=False,
                                               save_as=save_as.replace('ifu', 'rc'),
                                               offset_to_ifu=offset_to_ifu, epoch=epoch,
                                               non_sid_targ=non_sid_targ)
                if 'data' not in ret:
                    if mark_status:
                        # Update stuff
                        pass
                    return {'elaptime': time.time() - start, 'error': ret}

            else:
                ret = self.ocs.tel_move(name=name, ra=ra, dec=dec,
                                        equinox=equinox, ra_rate=ra_rate,
                                        dec_rate=dec_rate,
                                        motion_flag=motion_flag,
                                        epoch=epoch)

                ret = self.ocs.tel_offset(-98.5, -111.0)

        if guide:
            logger.debug("Beginning guider sequence")
            try:
                t = Thread(target=self.run_guider_seq, kwargs={'cam': self.rc,
                                                               'guide_length': exptime,
                                                               'guide_exptime': guide_exptime,
                                                               'readout': guide_readout,
                                                               'shutter': guide_shutter,
                                                               'name': name,
                                                               'email': email,
                                                               'objfilter': objfilter,
                                                               'req_id': req_id,
                                                               'obj_id': obj_id,
                                                               'test': '',
                                                               'is_rc': True,
                                                               'object_ra': ra,
                                                               'object_dec': dec,
                                                               'p60prid': p60prid,
                                                               'p60prpi': p60prpi,
                                                               'p60prnm': p60prnm})
                t.daemon = True
                t.start()
            except Exception as e:
                logger.exception("Error running the guider command")
                print(str(e))

        count = 1
        ret = ""
        if abpair:
            exptime = math.floor(exptime / 2)
            imgset = 'A'
            count = 2

        for i in range(count):
            if abpair:
                if i == 1:
                    imgset = 'B'
            ret = self.take_image(cam, exptime=exptime,
                                  shutter=shutter, readout=readout,
                                  start=start, save_as=save_as, test=test,
                                  imgtype=imgtype, objtype=objtype,
                                  object_ra=ra, object_dec=dec,
                                  email=email, p60prid=p60prid, p60prpi=p60prpi,
                                  p60prnm=p60prnm, obj_id=obj_id,
                                  req_id=req_id, objfilter=objfilter,
                                  imgset=imgset,
                                  is_rc=is_rc, abpair=abpair, name=name)
            print(ret, "Standard Done")
            if 'data' in ret and mark_status:
                self.sky.update_target_request(req_id, status='COMPLETED')
                print(ret)

        if 'data' in ret:
            return {'elaptime': time.time() - start,
                    'data': ret['data']}

    def run_acquisition_ifumap(self, cam, ra=None, dec=None, equinox=2000,
                               ra_rate=0.0, dec_rate=0.0, motion_flag="",
                               exptime=300, readout=2.0, shutter='normal',
                               move=True, name='Simulated', obj_id=-999,
                               req_id=-999, retry_on_failed_astrometry=False,
                               tcsx=False, test="", p60prid="", p60prnm="",
                               p60prpi="", email="",
                               retry_on_sao_on_failed_astrometry=False,
                               save_as=None, offset_to_ifu=False, epoch="",
                               non_sid_targ=False):
        """
        :return:
        :param cam:
        :param obj_id:
        :param req_id:
        :param test:
        :param p60prid:
        :param p60prnm:
        :param p60prpi:
        :param email:
        :param exptime:
        :param readout:
        :param shutter:
        :param move:
        :param name:
        :param retry_on_failed_astrometry:
        :param tcsx:
        :param ra:
        :param dec:
        :param retry_on_sao_on_failed_astrometry:
        :param save_as:
        :param equinox:
        :param ra_rate:
        :param dec_rate:
        :param motion_flag:
        :param offset_to_ifu:
        :param epoch:
        :param non_sid_targ:
        :return:
        """

        start = time.time()

        # Start by moving to the target using the input rates
        if move:
            logger.info("Moving to target")
            ret = self.ocs.tel_move(name=name, ra=ra, dec=dec, equinox=equinox,
                                    ra_rate=ra_rate, dec_rate=dec_rate,
                                    motion_flag=motion_flag, epoch=epoch)
            logger.info(ret)
            print(ret)

            if "error" in ret:
                ret = self.ocs.tel_move(name=name, ra=ra, dec=dec, equinox=equinox,
                                        ra_rate=ra_rate, dec_rate=dec_rate,
                                        motion_flag=motion_flag, epoch=epoch)
                print(ret, "SECOND RETURN")
            # Stop sidereal tracking until after the image is completed
            if non_sid_targ:
                self.ocs.set_rates(ra=0, dec=0)

        ret = self.take_image(self.rc, shutter=shutter, readout=readout,
                              name=name, start=start, test=test,
                              save_as=save_as, imgtype='Acq_ifumap',
                              objtype='Acq_ifumap', exptime=30,
                              object_ra=ra, object_dec=dec, email=email,
                              p60prid=p60prid, p60prpi=p60prpi,
                              p60prnm=p60prnm,
                              obj_id=obj_id, req_id=req_id,
                              objfilter='r', imgset='NA',
                              is_rc=False, abpair=False)
        print(ret)
        ret = self.sky.solve_offset_new(ret['data'], return_before_done=False)
        print(ret)
        if 'data' in ret:
            ra = ret['data']['ra_offset']
            dec = ret['data']['dec_offset']
            ret = self.ocs.tel_offset(ra, dec)
            print(ret)


        offsets = [{'ra': 0, 'dec': 0}, {'ra': -5, 'dec': 0}, {'ra': 10, 'dec': 0}, {'ra': -5, 'dec': -5},
                   {'ra': 0, 'dec': 10}]

        for offset in offsets:
            ret = self.ocs.tel_offset(offset['ra'], offset['dec'])
            print(ret)
            ret = self.take_image(cam, shutter=shutter, readout=readout,
                                  name=name, start=start, test=test,
                                  save_as=save_as, imgtype='Acq_ifumap',
                                  objtype='Acq_ifumap', exptime=exptime,
                                  object_ra=ra, object_dec=dec, email=email,
                                  p60prid=p60prid, p60prpi=p60prpi,
                                  p60prnm=p60prnm,
                                  obj_id=obj_id, req_id=req_id,
                                  objfilter='r', imgset='NA',
                                  is_rc=False, abpair=False)
            print(ret)
        return {'elaptime': time.time() - start, 'data': offsets}

    def _prepare_keys(self, obsdict):
        start = time.time()
        key_dict = {}
        print(obsdict.keys())
        # time.sleep(100)

        if 'imgtype' not in obsdict:
            key_dict['imgtype'] = 'Science'
        else:
            key_dict['imgtype'] = obsdict['imgtype']

        if 'equinox' not in obsdict:
            key_dict['equinox'] = 2000
        else:
            key_dict['equinox'] = obsdict['equinox']

        if 'epoch' not in obsdict:
            key_dict['epoch'] = ""
        else:
            key_dict['epoch'] = obsdict['epoch']

        if 'ra_rate' not in obsdict:
            key_dict['ra_rate'] = 0
        else:
            key_dict['ra_rate'] = obsdict['ra_rate']

        if 'dec_rate' not in obsdict:
            key_dict['dec_rate'] = 0
        else:
            key_dict['dec_rate'] = obsdict['dec_rate']

        if 'motion_flag' not in obsdict:
            key_dict['motion_flag'] = 0
        else:
            key_dict['motion_flag'] = obsdict['motion_flag']

        if 'p60prpi' not in obsdict:
            key_dict['p60prpi'] = self.p60prpi
        else:
            key_dict['p60prpi'] = obsdict['p60prpi']

        if 'p60prid' not in obsdict:
            key_dict['p60prid'] = self.p60prid
        else:
            key_dict['p60prid'] = obsdict['p60prid']

        if 'p60prnm' not in obsdict:
            key_dict['p60prnm'] = self.p60prnm
        else:
            key_dict['p60prnm'] = obsdict['p60prnm']

        if 'req_id' not in obsdict:
            key_dict['req_id'] = self.req_id
        else:
            key_dict['req_id'] = obsdict['req_id']

        if 'obj_id' not in obsdict:
            key_dict['obj_id'] = self.req_id
        else:
            key_dict['obj_id'] = obsdict['obj_id']

        if 'non_sid_targ' not in obsdict:
            key_dict['non_sid_targ'] = False
        else:
            key_dict['non_sid_targe'] = obsdict['non_sid_targ']

        if 'guide_exptime' not in obsdict:
            key_dict['guide_exptime'] = 30
        else:
            key_dict['guide_exptime'] = obsdict['guide_exptime']

        if 'email' not in obsdict:
            key_dict['email'] = ""
        else:
            key_dict['email'] = obsdict['email']

        return {'elaptime': time.time() - start, 'data': key_dict}

    def observe_by_dict(self, obsdict, move=True, run_acquisition_ifu=True,
                        run_acquisition_rc=False, guide=True, test="",
                        mark_status=True):
        """

        :param run_acquisition_rc:
        :param guide:
        :param test:
        :param mark_status:
        :param obsdict:
        :param move:
        :param run_acquisition_ifu:
        :return:
        """
        start = time.time()
        print(datetime.datetime.utcnow())

        if isinstance(obsdict, str):
            path = obsdict
            with open(path) as data_file:
                obsdict = json.load(data_file)
        elif not isinstance(obsdict, dict):
            return {'elaptime': time.time() - start,
                    'error': 'Input is neither json file or dictionary'}

        # Check required keywords
        if not all(key in obsdict for key in self.required_sciobs_keywords):
            return {'elaptime': time.time() - start,
                    'error': 'Missing one or more required keyword'}

        # Set any missing but non critical keywords
        ret = self._prepare_keys(obsdict)

        if 'data' not in ret:
            return {'elaptime': time.time() - start,
                    'error': 'Error prepping observing parameters'}
        kargs = ret['data']

        img_dict = {}
        # Now see if target has an ifu component
        pprint.pprint(obsdict)
        # time.sleep(1000)
        if obsdict['obs_dict']['ifu'] and self.run_ifu:
            pass
            ret = self.run_ifu_science_seq(self.ifu, name=obsdict['name'],
                                           test=test, ra=obsdict['ra'],
                                           dec=obsdict['dec'], readout=.1,
                                           exptime=obsdict['obs_dict']['ifu_exptime'],
                                           run_acquisition=run_acquisition_ifu,
                                           objtype='Transient',
                                           move_during_readout=True, abpair=False,
                                           guide=guide, move=move,
                                           mark_status=mark_status, **kargs)

            if 'data' in ret:
                img_dict['ifu'] = {'science': ret['data'],
                                   'guider': self.guider_list}

        if obsdict['obs_dict']['rc'] and self.run_rc:
            kargs.__delitem__('guide_exptime')
            print(kargs)
            ret = self.run_rc_science_seq(self.rc, name=obsdict['name'],
                                          test=test,
                                          ra=obsdict['ra'], dec=obsdict['dec'],
                                          run_acquisition=run_acquisition_rc, move=move,
                                          objtype='Transient',
                                          obs_order=obsdict['obs_dict']['rc_obs_dict']['obs_order'],
                                          obs_exptime=obsdict['obs_dict']['rc_obs_dict']['obs_exptime'],
                                          obs_repeat_filter=obsdict['obs_dict']['rc_obs_dict']['obs_repeat_filter'],
                                          repeat=1,
                                          move_during_readout=True,
                                          mark_status=mark_status, **kargs)
            if 'data' in ret:
                img_dict['rc'] = ret['data']

        print(datetime.datetime.utcnow())
        if 'data' in ret:
            return {'elaptime': time.time() - start, 'data': img_dict}
        else:
            return {'elaptime': time.time() - start, 'error': 'Image not acquired'}

    def run_ifu_science_seq(self, cam, shutter="normal",
                            readout=.1, name="",
                            test="", save_as="", imgtype='Science',
                            exptime=90, ra=0, dec=0, equinox=2000,
                            epoch="", ra_rate=0, dec_rate=0, motion_flag="",
                            p60prid='2018A-calib', p60prpi='SEDm', email='',
                            p60prnm='SEDm Calibration File', obj_id=-999,
                            objfilter='ifu', imgset='NA', is_rc=False,
                            run_acquisition=True, req_id=-999, acq_readout=2.0,
                            offset_to_ifu=True, objtype='Transient',
                            non_sid_targ=False, guide_readout=2.0,
                            move_during_readout=True, abpair=False,
                            guide=True, guide_shutter='normal', move=True,
                            guide_exptime=30,
                            retry_on_failed_astrometry=False,
                            mark_status=True, status_file=''):

        start = time.time()
        if mark_status:
            self.sky.update_target_request(req_id, status="ACTIVE")

        if move:
            if run_acquisition:
                ret = self.run_acquisition_seq(self.rc, ra=ra, dec=dec,
                                               equinox=equinox, ra_rate=ra_rate,
                                               dec_rate=dec_rate, motion_flag=motion_flag,
                                               exptime=30, readout=acq_readout,
                                               shutter=shutter, move=move, name=name,
                                               obj_id=obj_id, req_id=req_id,
                                               retry_on_failed_astrometry=retry_on_failed_astrometry,
                                               tcsx=False, test=test,
                                               p60prid=p60prid, p60prnm=p60prnm,
                                               p60prpi=p60prpi, email=email,
                                               retry_on_sao_on_failed_astrometry=False,
                                               save_as=save_as.replace('ifu', 'rc'),
                                               offset_to_ifu=offset_to_ifu, epoch=epoch,
                                               non_sid_targ=non_sid_targ)
                print(ret)
            else:
                ret = self.ocs.tel_move(name=name, ra=ra, dec=dec,
                                        equinox=equinox, ra_rate=ra_rate,
                                        dec_rate=dec_rate,
                                        motion_flag=motion_flag,
                                        epoch=epoch)

                print(self.ocs.tel_offset(-98.5, -111.0))

        if abpair:
            exptime = exptime / 2

        if guide:
            logger.debug("Beginning guider sequence")
            try:
                t = Thread(target=self.run_guider_seq, kwargs={'cam': self.rc,
                                                               'guide_length': exptime,
                                                               'guide_exptime': guide_exptime,
                                                               'readout': guide_readout,
                                                               'shutter': guide_shutter,
                                                               'name': name,
                                                               'email': email,
                                                               'objfilter': objfilter,
                                                               'req_id': req_id,
                                                               'obj_id': obj_id,
                                                               'test': '',
                                                               'imgset': imgset,
                                                               'is_rc': True,
                                                               'object_ra': ra,
                                                               'object_dec': dec,
                                                               'p60prid': p60prid,
                                                               'p60prpi': p60prpi,
                                                               'p60prnm': p60prnm})
                t.daemon = True
                t.start()
            except Exception as e:
                logger.exception("Error running the guider command")
                print(str(e))

        ret = self.take_image(cam, exptime=exptime,
                              shutter=shutter, readout=readout,
                              start=start, save_as=save_as, test=test,
                              imgtype=imgtype, objtype=objtype,
                              object_ra=ra, object_dec=dec,
                              email=email, p60prid=p60prid, p60prpi=p60prpi,
                              p60prnm=p60prnm, obj_id=obj_id,
                              req_id=req_id, objfilter=objfilter,
                              imgset='A', verbose=True,
                              is_rc=is_rc, abpair=abpair, name=name)

        if abpair:
            self.ocs.tel_offset(-5, 5)
            if guide:
                logger.debug("Beginning guider sequence")
                try:
                    t = Thread(target=self.run_guider_seq, kwargs={'cam': self.rc,
                                                                   'guide_length': exptime,
                                                                   'guide_exptime': guide_exptime,
                                                                   'readout': guide_readout,
                                                                   'shutter': guide_shutter,
                                                                   'name': name,
                                                                   'email': email,
                                                                   'objfilter': objfilter,
                                                                   'req_id': req_id,
                                                                   'obj_id': obj_id,
                                                                   'test': '',
                                                                   'imgset': imgset,
                                                                   'is_rc': True,
                                                                   'object_ra': ra,
                                                                   'object_dec': dec,
                                                                   'p60prid': p60prid,
                                                                   'p60prpi': p60prpi,
                                                                   'p60prnm': p60prnm})
                except Exception as e:
                    logger.exception("Error running the guider command")
                    print(str(e))

            ret = self.take_image(cam, exptime=exptime,
                                  shutter=shutter, readout=readout,
                                  start=start, save_as=save_as, test=test,
                                  imgtype=imgtype, objtype=objtype,
                                  object_ra=ra, object_dec=dec,
                                  email=email, p60prid=p60prid, p60prpi=p60prpi,
                                  p60prnm=p60prnm, obj_id=obj_id,
                                  req_id=req_id, objfilter=objfilter,
                                  imgset='B',
                                  is_rc=is_rc, abpair=abpair, name=name)

        if 'data' in ret and mark_status:
            self.sky.update_target_request(req_id, status='COMPLETED')
            print(ret)
        else:
            self.sky.update_target_request(req_id, status='FAILURE')

        return ret

    def run_rc_science_seq(self, cam, shutter="normal", readout=.1, name="",
                           test="", save_as="", imgtype='Science',
                           ra=0, dec=0, equinox=2000,
                           epoch="", ra_rate=0, dec_rate=0, motion_flag="",
                           p60prid='2018A-calib', p60prpi='SEDm', email='',
                           p60prnm='SEDm Calibration File', obj_id=-999,
                           objfilter='ifu', imgset='NA', is_rc=True,
                           run_acquisition=True, req_id=-999, acq_readout=2.0,
                           objtype='Transient', obs_order=None, obs_exptime=None,
                           obs_repeat_filter=None, repeat=1, non_sid_targ=False,
                           move_during_readout=True, abpair=False,
                           move=True,
                           retry_on_failed_astrometry=False,
                           mark_status=True, status_file=''):
        start = time.time()
        object_ra = ra
        object_dec = dec

        if mark_status:
            self.sky.update_target_request(req_id, status="ACTIVE")

        if move:
            if run_acquisition:
                ret = self.run_acquisition_seq(self.rc, ra=ra, dec=dec,
                                               equinox=equinox, ra_rate=ra_rate,
                                               dec_rate=dec_rate, motion_flag=motion_flag,
                                               exptime=1, readout=acq_readout,
                                               shutter=shutter, move=move, name=name,
                                               obj_id=obj_id, req_id=req_id,
                                               retry_on_failed_astrometry=retry_on_failed_astrometry,
                                               tcsx=True, test=test,
                                               p60prid=p60prid, p60prnm=p60prnm,
                                               p60prpi=p60prpi, email=email,
                                               retry_on_sao_on_failed_astrometry=False,
                                               save_as=save_as.replace('ifu', 'rc'),
                                               offset_to_ifu=False, epoch=epoch,
                                               non_sid_targ=non_sid_targ)
                if 'data' not in ret:
                    if mark_status:
                        # Update stuff
                        pass
                    return {'elaptime': time.time() - start, 'error': ret}

            else:
                ret = self.ocs.tel_move(name=name, ra=ra, dec=dec,
                                        equinox=equinox, ra_rate=ra_rate,
                                        dec_rate=dec_rate,
                                        motion_flag=motion_flag,
                                        epoch=epoch)

        ret = rc_filter_coords.offsets(ra=ra, dec=dec)
        print(ret)
        if 'data' in ret:
            obs_coords = ret['data']
        else:
            print("ERROR")
            return {'elaptime': time.time() - start,
                    'error': "Unable to calculate filter coordinates"}

        img_dict = {}
        print(obs_coords)

        if isinstance(obs_order, str):
            obs_order = obs_order.split(',')
        if isinstance(obs_repeat_filter, str):
            obs_repeat_filter = obs_repeat_filter.split(',')
        if isinstance(obs_exptime, str):
            obs_exptime = obs_exptime.split(',')

        for i in range(repeat):
            for j in range(len(obs_order)):
                objfilter = obs_order[j]
                if move:
                    ret = self.ocs.tel_move(ra=obs_coords[objfilter]['ra'],
                                            dec=obs_coords[objfilter]['dec'],
                                            equinox=equinox,
                                            ra_rate=ra_rate,
                                            dec_rate=dec_rate,
                                            motion_flag=motion_flag,
                                            name=name,
                                            epoch=epoch)
                    if 'data' not in ret:
                        continue
                for k in range(int(obs_repeat_filter[j])):
                    ret = self.take_image(cam, exptime=float(obs_exptime[j]),
                                          shutter=shutter, readout=readout,
                                          start=start, save_as=save_as,
                                          test=test,
                                          imgtype=imgtype, objtype=objtype,
                                          object_ra=object_ra, object_dec=object_dec,
                                          email=email, p60prid=p60prid,
                                          p60prpi=p60prpi,
                                          p60prnm=p60prnm, obj_id=obj_id,
                                          req_id=req_id, objfilter=objfilter,
                                          imgset='NA', is_rc=is_rc, abpair=abpair,
                                          name=name)
                    if 'data' in ret:
                        print(objfilter, ret)
                        if objfilter in img_dict:
                            img_dict[objfilter] += ', %s' % ret['data']
                        else:
                            img_dict[objfilter] = ret['data']
        if mark_status:
            self.sky.update_target_request(req_id, status="COMPLETED")

        return {'elaptime': time.time() - start, 'data': img_dict}

    def run_acquisition_seq(self, cam, ra=None, dec=None, equinox=2000,
                            ra_rate=0.0, dec_rate=0.0, motion_flag="",
                            exptime=30, readout=2.0, shutter='normal',
                            move=True, name='Simulated', obj_id=-999,
                            req_id=-999, retry_on_failed_astrometry=False,
                            tcsx=False, test="", p60prid="", p60prnm="",
                            p60prpi="", email="",
                            retry_on_sao_on_failed_astrometry=False,
                            save_as=None, offset_to_ifu=True, epoch="",
                            non_sid_targ=False):
        """

        :return:
        :param cam:
        :param obj_id:
        :param req_id:
        :param test:
        :param p60prid:
        :param p60prnm:
        :param p60prpi:
        :param email:
        :param exptime:
        :param readout:
        :param shutter:
        :param move:
        :param name:
        :param retry_on_failed_astrometry:
        :param tcsx:
        :param ra:
        :param dec:
        :param retry_on_sao_on_failed_astrometry:
        :param save_as:
        :param equinox:
        :param ra_rate:
        :param dec_rate:
        :param motion_flag:
        :param offset_to_ifu:
        :param epoch:
        :param non_sid_targ:
        :return:
        """

        start = time.time()

        # Start by moving to the target using the input rates
        if move:
            ret = self.ocs.tel_move(name=name, ra=ra, dec=dec, equinox=equinox,
                                    ra_rate=ra_rate, dec_rate=dec_rate,
                                    motion_flag=motion_flag, epoch=epoch)
            print(ret)
            # Stop sidereal tracking until after the image is completed
            if non_sid_targ:
                self.ocs.set_rates(ra=0, dec=0)

        ret = self.take_image(cam, shutter=shutter, readout=readout,
                              name=name, start=start, test=test,
                              save_as=save_as, imgtype='Acquisition',
                              objtype='Acquisition', exptime=exptime,
                              object_ra=ra, object_dec=dec, email=email,
                              p60prid=p60prid, p60prpi=p60prpi,
                              p60prnm=p60prnm,
                              obj_id=obj_id, req_id=req_id,
                              objfilter='r', imgset='NA',
                              is_rc=True, abpair=False)
        print(ret)
        if 'data' in ret:
            ret = self.sky.solve_offset_new(ret['data'], return_before_done=True)
            print(ret)
            if move and offset_to_ifu and not tcsx:
                print(self.ocs.tel_offset(-98.5, -111.0))
            ret = self.sky.listen()
            print(ret)
            if 'data' in ret:
                ra = ret['data']['ra_offset']
                dec = ret['data']['dec_offset']
                ret = self.ocs.tel_offset(ra, dec)
                if tcsx and move and offset_to_ifu:
                    if abs(ra) < 100 and abs(dec) < 100:
                        print(self.ocs.telx())
                    print(self.ocs.tel_offset(-98.5, -111.0))
                if non_sid_targ:
                    elapsed = time.time() - start
                    ra_rate_off = round(ra_rate * (elapsed / 3600), 2)
                    dec_rate_off = round(dec_rate * (elapsed / 3600), 2)
                    ret = self.ocs.tel_offset(ra_rate_off, dec_rate_off)
                    print(ret)
                    ret = self.ocs.set_rates(ra=ra_rate, dec=dec_rate)
                    print(ret)
                return {'elaptime': time.time() - start,
                        'data': 'Telescope in place with calculated offsets'}
            else:
                if non_sid_targ:
                    elapsed = time.time() - start
                    ra_rate_off = round(ra_rate * (elapsed / 3600), 2)
                    dec_rate_off = round(dec_rate * (elapsed / 3600), 2)
                    ret = self.ocs.tel_offset(ra_rate_off, dec_rate_off)
                    print(ret)
                    ret = self.ocs.set_rates(ra=ra_rate, dec=dec_rate)
                    print(ret)
                    return {'elaptime': time.time() - start,
                            'data': 'Telescope in place with calculated offsets'
                                    'and blind pointing'}
                else:
                    return {'elaptime': time.time() - start,
                            'data': 'Telescope in place with blind pointing'}

        else:
            return {'elaptime': time.time() - start,
                    'error': 'Error acquiring acquisition image'}

    def find_nearest(self, target_file, obsdate=None):
        """
        Find the nearest observation time
        :param target_file:
        :param obsdate:
        :return:
        """
        start = time.time()
        df = pd.read_csv(target_file)
        df['time'] = pd.to_datetime(df['time'])

        df.set_index('time', inplace=True)

        if not obsdate:
            obsdate = datetime.datetime.utcnow()

        dt = pd.to_datetime(obsdate)

        total_ephems = len(df)
        print(total_ephems)
        print(df)
        if df.empty:
            return {"elaptime": time.time()-start,
                    "error": 'No data found in csv file'}

        idx = df.index.get_loc(dt, method='nearest')

        if idx == total_ephems-1:
            return {"elaptime": time.time()-start,
                    "error": 'Last value picked'}
        elif idx == 0:
            return {"elaptime": time.time()-start,
                    "error": 'First value picked'}

        print("idx", idx)
        uttime = df.index[idx]
        decimal_time = uttime.hour + ((uttime.minute * 60) + uttime.second)/3600.0

        # Create observing dict
        return_dict = {
            'name': df['name'][idx],
            'ra': df['ra'][idx],
            'dec': df['dec'][idx],
            'ra_rate': df['ra_rate'][idx],
            'dec_rate': df['dec_rate'][idx],
            'mag': df['V'][idx],
            'uttime': decimal_time
        }

        return {"elaptime": time.time()-start, "data": return_dict}

    def get_nonsideral_target(self, target_file='', target="", obsdate='', target_dir=''):
        """

        :param target_file:
        :param target:
        :param obsdate:
        :param target_dir:
        :return:
        """
        start = time.time()
        ret = ""
        if not target_file:
            if not obsdate:
                obsdate_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
                obsdate = datetime.datetime.utcnow()
            else:
                obsdate_date = obsdate.split()[0]

            print("Nonsidereal obsdate", obsdate)
            if not target_dir:
                target_dir = self.non_sidereal_dir

            print("Nonsidereal target directory", target_dir)
            if target:
                target_file = os.path.join(target_dir, '%s.%s.csv' % (target, obsdate_date))

            if not target_file:
                print("Search string:", '%s*.%s.csv' % (target_dir, obsdate_date))
                available_targets = glob.glob('%s*.%s.csv' % (target_dir, obsdate_date))
                print("Nonsidereal Available targets", available_targets)
                if len(available_targets) == 0:
                    return {'elaptime': time.time()-start, 'error': 'No targets available'}

                for t in available_targets:
                    ret = self.find_nearest(t, obsdate=obsdate)
                    if 'data' in ret:
                        shutil.move(t, t.replace('.csv', 'txt.observed'))
                        break
        else:
            ret = self.find_nearest(target_file, obsdate=obsdate)

        if not ret:
            return {"elaptime": time.time()-start, "error": "No target found"}

        return ret

    def conditions_cleared(self):
        faults = self.ocs.check_faults()
        print(faults, "This is the faults")
        if 'data' in faults:
            if 'P200' in faults['data']:
                print("P200 fault")
                return False
            if 'WEATHER' in faults['data']:
                print("Weather fault")
                return False
        else:
            print("No faults could be found")
            return True

    def check_dome_status(self, open_if_closed=True):
        start = time.time()
        stat = self.ocs.check_status()

        if 'data' in stat:
            ret = stat['data']['dome_shutter_status']
            if 'closed' in ret.lower():
                print("Opening dome")
                if open_if_closed:
                    open_ret = self.ocs.dome("open")
                    return {'elaptime': time.time()-start,
                            'data': open_ret}
            else:
                return {'elaptime': time.time()-start,
                        'data': "Dome already open"}

        else:
            return {'elaptime': time.time() - start,
                    'error': stat}


    def run_manual_command(self, manual):
        start = time.time()
        obsdict = manual
        path = ""
        if isinstance(manual, str):
            path = manual
            with open(path) as data_file:
                obsdict = json.load(data_file)

        elif not isinstance(manual, dict):
            return {'elaptime': time.time() - start,
                    'error': 'Input is neither json file or dictionary'}

        if 'command' in obsdict:
            command = obsdict['command']
        else:
            if path:
                os.remove(path)

            return {'elaptime': time.time() - start,
                    'error': 'No command not found'}

        if command.lower() == "standard":
            ret = self.run_standard_seq(self.ifu)
            print(ret)
        elif command.lower() == "focus":
            if 'range' in obsdict:
                import numpy as np
                np.arange(16.45, 17.05, .05)
                ret = self.run_focus_seq(self.rc, 'rc_focus', name="Focus",
                                         foc_range=np.arange(obsdict['range'][0],
                                                             obsdict['range'][1],
                                                             obsdict['range'][2]))
                print(ret)
            else:
                ret = self.run_focus_seq(self.rc, 'rc_focus', name="Focus")
                print(ret)

        elif command.lower() == "nonsid_ifu":
            if "obsdate" in obsdict:
                obsdate = obsdict['obsdate']
            else:
                obsdate = ""

            if 'target' in obsdict:
                ret = self.get_nonsideral_target(target=obsdict['target'], obsdate=obsdate)
            else:
                ret = self.get_nonsideral_target(obsdate=obsdate)

            if 'data' not in ret:
                return {"elaptime": time.time()-start, "error": ret}

            nonsid_dict = ret['data']

            ret = self.run_ifu_science_seq(self.ifu, name=nonsid_dict['name'],
                                           imgtype='Science',
                                           exptime=1200, ra=nonsid_dict['ra'],
                                           dec=nonsid_dict['dec'],
                                           equinox=2000,
                                           epoch=nonsid_dict['uttime'],
                                           ra_rate=nonsid_dict['ra_rate'],
                                           dec_rate=nonsid_dict['dec_rate'],
                                           motion_flag=1,
                                           p60prid='2019B-Asteroids',
                                           p60prpi='SEDm',
                                           email='',
                                           p60prnm='Near-Earth Asteroid Spectra',
                                           objfilter='ifu',
                                           run_acquisition=True,
                                           objtype='Transient',
                                           non_sid_targ=True,
                                           guide_readout=2.0,
                                           move_during_readout=True,
                                           abpair=False,
                                           guide=False,
                                           guide_shutter='normal',
                                           move=True,
                                           guide_exptime=30,
                                           retry_on_failed_astrometry=False,
                                           mark_status=True, status_file='')

            print(ret)

        if path:
            os.remove(path)

if __name__ == "__main__":
    x = SEDm()
    x.initialize()
    x.take_bias(x.ifu, N=1, test=' test')

