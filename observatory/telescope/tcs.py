import os
import socket
import json
import time
import yaml

from utils.sedmlogging import setup_logger


# Open the config file
SR = os.path.abspath(os.path.dirname(__file__) + '/../../')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)

# Setup logger
name = "TCSLogger"
logfile = os.path.join(params['logging']['logpath'], 'tcs.log')
logger = setup_logger(name, log_file=logfile)


class Telescope:
    """Top level class to handle all the GXN commands and to make sure they
    are properly formatted.  Commands return True and time to complete command
    if successful.  Otherwise False and an error message when a command fails
    """

    def __init__(self, simulated=False, gxnaddress=None):

        self.simulated = simulated
        self.dome_states = ['OPEN', 'CLOSE']
        self.delimiter = "="
        self.weather = {}
        self.pos = {}
        self.status = {}
        self.faults = {}
        self.socket = None
        self.error_tracker = 0
        with open(os.path.join(SR, 'config', 'tcs.json')) as data_file:
            self.tcs_config = json.load(data_file)

        if not gxnaddress:
            self.address = (params['observatory']['tcs']['gxn']['ip'],
                            params['observatory']['tcs']['gxn']['port'])
        else:
            self.address = gxnaddress
            
        # These command should have an instanteous return
        self.fast_commands = ['?POS', '?STATUS', '?WEATHER', '?FAULTS',
                              'TAKECONTROL', 'MRATES', 'SAO', 'LAMPOFF',
                              'LASTX', 'GIVECONTROL', 'STOP', 'X', 'TX',
                              'Z', 'COORDS', 'INZP', 'RATES', 'RATESS']

        self.slow_commands = ['TELINIT', 'OPEN', 'CLOSE', 'GOPOS', 'GOREF',
                              'N', 'S', 'E', 'W', 'ES', 'WS', 'PT', 'STOW',
                              'INCFOCUS', 'PTS',  'IRATES', 'GOFOCUS',
                              'GODOME', 'CLOSED', 'LAMPON']

        self.commands_with_parameters = ['COORDS', 'MRATES', 'N', 'S', 'ES',
                                         'WS', 'RATES', 'RATESS', 'INZP',
                                         'PTS', 'IRATES', 'E', 'W', 'PT',
                                         'STOW', 'GOFOCUS', 'GODOME', 'SAO',
                                         'INCFOCUS']

        self.info_commands = ['?POS', '?STATUS', '?WEATHER', '?FAULTS']
        self.takecontrol()

    def __connect(self):
        logger.info("Connecting to address:%s", self.address)
        try:
            self.socket = socket.socket()
            self.socket.connect((self.address))
        except Exception as e:
            logger.error("Error connecting to the GXN:%s", str(e),
                         exc_info=True)
            self.socket = None
            pass
        return self.socket
    
    # CONTROL COMMANDS:
    def send_command(self, cmd="", parameters=None,
                     error_handling=True):
        """
        Send one of the GXN commands to the server.
        :param cmd: Predefined "fast" or "slow" commands
        :param parameters: List of parameters that go with the specified cmd
        :param timeout: amount in seconds to wait for a command to time out
        :return: Bool,time to complete command in seconds
        """
        # Start timer
        start = time.time()
        origin_command = cmd
        origin_params = parameters

        info = False
        # Check if the socket is open
        if not self.socket:
            logger.info("Socket not connected")
            self.socket = self.__connect()
            if not self.socket:
                return {"elaptime": time.time()-start,
                        "error": "Error connecting to the GXN adderess"}

        # Make sure all commands are upper case
        cmd = cmd.upper()

        # 1.Check to see if it is a fast or slow command
        if cmd in self.fast_commands:
            self.socket.settimeout(60)
            if cmd in self.info_commands:
                info = True
            logger.info("Sending fast command with 60s timeout")
        elif cmd in self.slow_commands:
            self.socket.settimeout(300)
            logger.info("Sending slow command with 300s timeout")
        else:
            logger.error("Command '%s' is not a valid GXN command", cmd,
                         exc_info=True)
            return {"elaptime": time.time() - start,
                    "error": "Error with input commamd:%s" % cmd}

        # 2. Check if command is in the commands with parameters list.  If yes
        # and parameters are not listed return false
        if cmd in self.commands_with_parameters and not parameters:
            return {"elaptime": time.time() - start,
                    "error": "Error commamd:%s should have parameters" % cmd}

        elif cmd in self.commands_with_parameters and isinstance(parameters,
                                                                 list):
            cmd += " "
            parameters = [str(x) for x in parameters]
            cmd += " ".join(parameters)

        # 3. At this point we have the full command for the GXN interface
        try:
            logger.info("Sending:%s", cmd)
            self.socket.send(b"%s \r" % cmd.encode('utf-8'))
        except Exception as e:
            logger.error("Error sending command: %s", str(e), exc_info=True)
            return {"elaptime": time.time() - start,
                    "error": "Error commamd:%s failed" % cmd}

        # 4. Get the return response
        try:
            # Slight delay added for the info command to print out
            if info:
                time.sleep(.05)

            ret = self.socket.recv(2048)

            # Return the int code
            if ret:
                ret = ret.decode('utf-8')
            else:
                # Try one more time to get a return
                ret = self.socket.recv(2048)

            # If we still don't have a return then something has gone wrong.
            if not ret:
                logger.error("No response given back from the GXN interface")
                return {"elaptime": time.time() - start,
                        "error": "No response from TCS"}

            # Return the info product or return code
            logger.info("Received: %s", ret)
            if info:
                return {"elaptime": time.time() - start,
                        "data": ret.rstrip('\0')}
            else:
                try:
                    if isinstance(ret, str):
                        ret = ret.rstrip('\0')
                        if len(ret) <= 2:
                            int_code = int(ret.rstrip('\0'))
                            if int_code == 0:
                                return {"elaptime": time.time() - start,
                                        "data": "Success"}
                            else:
                                if error_handling:
                                    if self.error_tracker >= 2:
                                        self.error_tracker = 0
                                        return {"elaptime": time.time() - start,
                                                "error": self.check_return(int_code)}

                                    if int_code == -3:
                                        logger.error("%s: command can't be executed", cmd)
                                        time.sleep(5)
                                        self.error_tracker += 1
                                        print("Command can't be executed so "
                                              "waiting 5s and trying again")
                                        ret = self.send_command(cmd=origin_command,
                                                                 parameters=origin_params)
                                        if 'data' in ret:
                                            return {'elaptime': time.time()-start,
                                                    'data': ret['data']}
                                        elif 'error' in ret:
                                            return {'elaptime': time.time()-start,
                                                    'error': ret['error']}
                                        else:
                                            return ret

                                    if int_code == -6:
                                        logger.error("Robot does not have control")
                                        self.error_tracker += 1
                                        ret = self.takecontrol()
                                        if 'error' in ret:
                                            return {'elaptime': time.time()-start,
                                                    'error': "Unable to take "
                                                             "control of telescope"}
                                        else:
                                            return self.send_command(cmd=origin_command,
                                                                     parameters=origin_params)

                                return {"elaptime": time.time() - start,
                                        "error": self.check_return(int_code)}
                        else:
                            return {"elaptime": time.time() - start,
                                    "error": "Added output to "
                                             "TCS return string:%s" % ret}
                    else:
                        print("Unknown TCS return")
                        return {"elaptime": time.time()-start,
                                "error": "Unknown TCS return value"}
                except Exception as e:
                    logger.error("Unbable to convert telescope return to int",
                                 exc_info=True)
                    return {"elaptime": time.time() - start,
                            "error": str(e)}
        except Exception as e:
            logger.error("Unkown error",
                         exc_info=True)
            return {"elaptime": time.time() - start,
                    "error": str(e)}

    def check_return(self, int_return):
        """Non-ASCII-information commands return "0" in case of success, "-1" if
        the command is unknown, "-2" if a parameter is bad, "-3" if the command
        cannot be executed at the current time, "-5" if the command was aborted,
        "-6" if the GXN interface does not have control. """

        if int_return == 0:
            self.error_str = ""
        elif int_return == -1:
            self.error_str = "-1: Unknown Command"
        elif int_return == -2:
            self.error_str = "-2: Parameter is bad"
        elif int_return == -3:
            self.error_str = "-3: Command can't be executed at the moment"
        elif int_return == -5:
            self.error_str = "-5: Command was aborted"
        elif int_return == -6:
            self.error_str = "-6: GXN interface does not hace control"
        else:
            self.error_str = "%s: Unknown return" % int_return

        return self.error_str

    def takecontrol(self):
        """
        (FAST) requests that TCS control be given to GXN interface.
        Fails if ?STATUS item Telescope_Control_Status is not AVAILABLE.
        (No parameters)
        :return:bool,status message
        """
        return self.send_command(cmd="TAKECONTROL")

    def givecontrol(self):
        """
        GIVECONTROL (FAST) returns TCS control to TCS console.
        (No parameters)
        :return:bool,status message
        """
        return self.send_command(cmd="GIVECONTROL")

    def telinit(self):
        """
        (SLOW) tests for proper operation of telescope axis motors, dome
        drive, and focus drive, as well as encoders for each axis.  It also
        initializes secondary mirror vacuum.  It must be issued before tracking
        of target positions can occur.  This command only needs to be issued at
        the beginning of the night unless the telescope is powered down and
        then powered back up.  ?STATUS items Telescope_Power_Status and
        Oil_Pad_Status must be READY for this command to work.  The command
        fails if wetness is sensed.  When initialization is complete, focus
        is returned to its original setting and telescope and dome are left
        stopped in day stow position.
        (No parameters)
        :return:bool,status message
        """
        return self.send_command(cmd="TELINIT")

    def stop(self):
        """
        (FAST) aborts any currently-active telescope motion, including
        slewing, tracking, or offsetting.  ?POS item Telescope_Motion_Status
        will change to STOPPED.

        :return:bool,status message
        """
        return self.send_command(cmd="STOP")

    # DOME LAMPS
    def halogens_on(self):
        """
        (SLOW) turns on the flat field lamp.  Filament current is not
        settable through the TCS, but lamp status and current flow may be
        checked with the ?STATUS command.  Note that GOPOS, GOREF and STOW
        commands turn off the flat field lamp. (No parameters)

        :return:bool,status message
        """
        return self.send_command("LAMPON")

    def halogens_off(self):
        """
        (SLOW) turns on the flat field lamp.  Filament current is not
        settable through the TCS, but lamp status and current flow may be
        checked with the ?STATUS command.  Note that GOPOS, GOREF and STOW
        commands turn off the flat field lamp. (No parameters)

        :return:bool,status message
        """
        return self.send_command("LAMPOFF")

    # FOCUS COMMANDS
    def incfocus(self, offset=0):
        """
        INCFOCUS (SLOW) moves the telescope focus by the offset requested.
        The destination must fall in the range 4.5mm to 24mm.  ?STATUS item
        Telescope_Power_Status must be READY for this command to work.

        :param offset: focus offset in mm
        :return: bool, status message
        """
        try:
            offset = float(offset)
            if abs(offset) > 10:
                return False, "Offset too large"
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd="INCFOCUS", parameters=[offset])

    def gofocus(self, pos=14.2):
        """
        GOFOCUS (SLOW) moves the telescope focus to the position requested. The
        destination must fall in the range 4.5mm to 24mm.  ?STATUS item
        Telescope_Power_Status must be READY for this command to work.
        Parameters:
        :param pos: enter focus position in mm
        :return: bool, status message
        """

        try:
            pos = float(pos)
            if pos < 4.5 or pos > 24:
                return False, "%smm is out of range 4.5mm-24mm" % pos
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd="GOFOCUS", parameters=[pos])

    # OFFSET COMMANDS
    def offset_direction(self, direction="", offset=0):
        """
        N, S, E, W (SLOW) offsets the telescope position north, south, east or
        west respectively by the requested number of arcseconds, moving at the
        rate set by MRATES.  ?POS item Telescope_Motion_Status must be
        TRACKING or IN_POSITION for this command to work, and will change to
        MOVING during the move.  The command fails if wetness is sensed.
        Parameters:
        :param direction: string of either N,S,E,W
        :param offset: float
        :return: bool, status message
        """
        try:
            direction = direction.upper().strip()
            if direction not in self.offset_direction_list:
                return False, "%s is not a valid direction [N,S,E,W]"
            offset = round(float(offset), 2)
            if direction in ['N', 'S'] and abs(offset) >= 6000:
                return False, '%s is larger than 6000" limit for DEC' % offset
            elif direction in ['E', 'W'] and abs(offset) >= 600:
                return False, '%s is larger than 600" limit for RA' % offset
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd=direction, parameters=[offset])

    def offset_by_time(self, direction="", duration=""):
        """
        ES, WS (SLOW) offsets the telescope position east or west respectively by
        the requested number of seconds of time, moving at the rate set by MRATES.
        ?POS item Telescope_Motion_Status must be TRACKING or IN_POSITION for this
        command to work, and will change to MOVING during the move.  The command
        fails if wetness is sensed.

        :param direction: ES WS
        :param duration: float in seconds ,max 600s
        :return: bool, status message
        """
        try:
            direction = direction.upper().strip()
            if direction not in self.offset_direction_time_list:
                return False, "%s is not a valid direction [ES,WS]"
            duration = round(float(duration), 3)
            if duration >= 600:
                return False, '%ss is larger than 600s limit' % duration
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd=direction, parameters=[duration])

    def offset(self, ra=0, dec=0):
        """
        PT (SLOW) offsets the telescope position by the requested amount,
        moving at the rate set by MRATES.  ?POS item Telescope_Motion_Status
        must be TRACKING or IN_POSITION for this command to work, and will
        change to MOVING during the move.  The command fails if wetness is
        sensed.

        :param ra: offset in seconds
        :param dec: offset in arcseconds
        :return: bool, status message
        """

        try:
            offsets = [round(float(x), 2) for x in [ra, dec]]
            if abs(offsets[0]) >= 600:
                return False, '%ss is larger than 600" RA limit' % offsets[0]
            if abs(offsets[1]) >= 6000:
                return False, '%ss is larger than 6000" DEC limit' % offsets[1]
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd="PT", parameters=offsets)

    def pt_offset_time(self, ra=0, dec=0):
        """
        PTS (SLOW) similar to PT offsets the telescope position by the
        requested amount, moving at the rate set by MRATES, but the RA distance
        is angular second of time. ?POS item Telescope_Motion_Status must be
        TRACKING or IN_POSITION for this command to work, and will change to
        MOVING during the move.  The command fails if wetness is sensed.

        :param ra: offset in seconds
        :param dec: offset in arcseconds
        :return: bool, status message
        """

        try:
            offsets = [round(float(x), 3) for x in [ra, dec]]
            if abs(offsets[0]) >= 600:
                return False, '%ss is larger than 600s RA limit' % offsets[0]
            if abs(offsets[1]) >= 6000:
                return False, '%ss is larger than 6000" DEC limit' % offsets[1]
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd="PTS", parameters=offsets)

    def mrates(self, rate=25):
        """
        (FAST) sets the rate of telescope offset moves described above.
        Move will proceed as a vector to the requested offset at the rate set
        by this command.

        :param rate: rate in arc/sec
        :return: bool, status message
        """

        try:
            rate = round(float(rate), 2)
            if rate < 1 or rate > 50:
                return False, '%s falls out of the 1-50"/sec rate range' % rate
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd="MRATES", parameters=[rate])

    def rates(self, ra=0, dec=0):
        """
        (FAST) as implemented at P60, specifies non-sidereal tracking rates
        that will be applied when GOPOS is next executed.  Better behavior
        might be to set non-sidereal rates to be applied immediately starting
        at the current position.

        :param ra: RA rate in arc/hour
        :param dec: DEC rate in arc/hour
        :return:bool, status message
        """

        try:
            rates = [round(float(x), 2) for x in [ra, dec]]
            if abs(rates[0]) >= 100000:
                return False, '%ss is larger than 100000"/hr RA limit' % rates[0]
            if abs(rates[1]) >= 100000:
                return False, '%ss is larger than 100000"/hr DEC limit' % rates[1]
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd="IRATES", parameters=rates)

    def irates(self, ra=0, dec=0):
        """
        NEW:  Same concept as rates but rates are now applied instantaneous.

        :param ra:
        :param dec:
        :return:
        """

        try:
            rates = [round(float(x), 2) for x in [ra, dec]]
            if abs(rates[0]) >= 100000:
                return False, '%ss is larger than 100000"/hr RA limit' % rates[0]
            if abs(rates[1]) >= 100000:
                return False, '%ss is larger than 100000"/hr DEC limit' % rates[1]
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd="IRATES", parameters=rates)

    def ratess(self, ra=0, dec=0):
        """
        (FAST) like RATES, but RA parameter specifies RA rate in
        seconds of time/hour.

        :param ra: RA rate in seconds/hour
        :param dec: DEC rate in arc/hour
        :return:bool, status message
        """

        try:
            rates = [round(float(x), 2) for x in [ra, dec]]
            if abs(rates[0]) >= 7200:
                return False, '%ss is larger than 7200s/hr RA limit' % rates[0]
            if abs(rates[1]) >= 100000:
                return False, '%ss is larger than 100000"/hr DEC limit' % rates[1]
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd="RATESS", parameters=rates)

    def stow(self, ha=0, dec=109, domeaz=90):
        """
        STOW (SLOW) sends the telescope and dome to the requested positions.
        Sanity checks are made to confirm that the requested telescope
        position is legal.
        Telescope position will be stationary upon arrival, and
        Telescope_Motion_Status as returned by ?POS will be IN_POSITION.
        The telescope need not be initialized for this command to work,
        but ?STATUS items Telescope_Power_Status and
        Oil_Pad_Status must be READY.  The command fails if wetness is sensed.
        Parameters:

        :param ha: Hour Angle position in decimal hours (positive west)
        :param dec: Dec position in decimal degrees
        :param domeaz: Dome azimuth in decimal degrees
        :return:
        """
        try:
            stow = [round(float(x), 3) for x in [ha, dec, domeaz]]
            if abs(stow[0]) >= 24:
                return False, '%ss is larger than HA hour limit' % stow[0]
            if abs(stow[1]) >= 109.1:
                return False, '%ss is larger than DEC limit' % stow[1]
            if abs(stow[2]) >= 360.01:
                return False, '%ss is larger than Domeaz limit' % stow[2]
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd="STOW", parameters=stow)

    # DOME COMMANDS
    def dome(self, state=""):
        """
        Dome function can be either OPEN or CLOSE
        CLOSE (SLOW) closes dome shutters after stowing the telescope in a safe
        position.  The command leaves the telescope and dome in indeterminate
        positions unless the telescope was previously stowed below 30 degrees
        elevation, in which case no telescope or dome motion will take place.
        ?STATUS items Telescope_Power_Status and Oil_Pad_Status must be READY
        for the telescope to be safely stowed, but if they are not ready, the
        shutters will close anyway unless the Emergency Switch is tripped.
        (No parameters)


        OPEN (SLOW) opens dome shutters after stowing the telescope in a safe
        position if the sun down, weather conditions do not exceed thresholds,
        and the P200 Telescope Operator is not commanding dome closure.  (Note
        that if any of these conditions becomes invalid, an asynchronous close
        can occur at any time.) The command leaves the telescope and dome in
        indeterminate positions unless the telescope was previously stowed
        below 30 degrees elevation, in which case no telescope or dome motion
        will take place.  ?STATUS items Telescope_Power_Status and
        Oil_Pad_Status must be READY for this command to work.
        NOTE (19Aug2004): OPEN is now permitted after 0hUT, provided other
        conditions permit.  Dome will go to 40 deg azimuth, and telescope will
        go to W0h HA and +90 dec.  These positions are locked until sunset.
        (No parameters)

        :param state: OPEN, CLOSE
        :return: bool, status message
        """

        state = state.upper().strip()
        if state == 'OPEN':
            return self.send_command("OPEN")
        elif state == 'CLOSE':
            return self.send_command("CLOSE")
        else:
            return -1, "%s is not a valid dome state OPEN, CLOSE" % state

    def godome(self, azimuth=0):
        """
        GODOME (SLOW) sends the dome to the requested azimuth.  ?STATUS item
        Telescope_Power_Status must be READY for this command to work.  The
        command fails if wetness is sensed.  This command overrides dome
        tracking of the telescope position until the next GOPOS or GOREF.

        :param azimuth: dome destination azimuth in degrees
        :return:
        """

        try:
            azimuth = round(float(azimuth), 2)
            if azimuth < 1 or azimuth > 50:
                return -1, '%s is not in range 0-360' % azimuth

        except Exception as e:
            return -1, str(e)

        return self.send_command(cmd="GODOME", parameters=[azimuth])

    # POINTING COMMANDS [DO NOT USE UNLESS YOU KNOW WHAT YOU ARE DOING]
    def x(self):
        """
        X (FAST) adjusts TCS internal offsets so telescope coordinates agree
        with the last GOPOS position.  The command fails if RA or Dec offset
        would change by more than 100 arcsec.  Original pointing offsets
        (from before the update) are saved and will be restored if LASTX is
        executed (LASTX).

        :return:bool, status message
        """
        return self.send_command(cmd="X")

    def tx(self):
        """
        (FAST) adjusts TCS internal offsets so telescope coordinates agree with
        the last GOPOS position.  The command fails if RA or Dec offset would
        change by more than 100 arcsec.  Previous offsets are not saved
        (ie, LASTX returns telescope pointing to the last offsets saved with
        an X command).

        :return:bool, status message
        """
        return self.send_command(cmd="TX")

    def lastx(self):
        """
        (FAST) restores pointing offsets saved when the X command was last
        executed.

        :return:bool, status message
        """
        return self.send_command(cmd="LASTX")

    def inzp(self, ra=0, dec=0):
        """
        (FAST) directly sets offset values used for pointing adjustment.
        :param ra: RA offset in arcseconds of time (positive for westward
                   offsets)
        :param dec: DEC offset in arcseconds of time (positive for northward
                    offsets)
        :return: bool, status message
        """

        try:
            offsets = [round(float(x), 3) for x in [ra, dec]]
            if abs(offsets[0]) >= 600:
                return False, '%ss is larger than 600s RA limit' % offsets[0]
            if abs(offsets[1]) >= 6000:
                return False, '%ss is larger than 6000" DEC limit' % offsets[1]
        except Exception as e:
            return False, str(e)

        return self.send_command(cmd="INZP", parameters=offsets)

    # TELESCOPE COORDINATE MOVES
    def coords(self, name=None, ra=0, dec=33, equinox=2000, ra_rate=0,
               dec_rate=0, motion_flag="", epoch=""):
        """
        (FAST) accepts information to specify a TARGET Position.  If no
        non-sidereal motion needs to be specified, parameters 6&7 may be
        omitted. An optional name, enclosed in double quotes(") and
        space-separated from other parameters, may be added anywhere in
        the command line.

        :type name: None
        :param name: Name of object
        :param ra: Right Ascension in decimal hours
        :param dec: Declination in decimal degrees
        :param equinox: Equinox of coordinates in decimal years -- zero means
                        apparent
        :param ra_rate: 0.0001sec/yr if flag (see motion_flag) is 0, arcsec/hr
                        if flag is 1, sec/hr if flag is 2
        :param dec_rate: 0.001 arcsec/yr if flag is 0, arcsec/hr if flag is 1
                         or 2
        :param motion_flag: 0=proper motion, which is the default if this
                            parameter is absent; 1=non-sidereal rates
                            (RA spatial rate), 2=non-sidereal rates
                            (RA angular rate)
        :param epoch: Epoch of coordinates for non-sidereal targets, in decimal
                      hours (current UTC if omitted)
        :return:
        """
        start = time.time()
        try:

            coords = [round(float(x), 5) for x in [ra, dec, equinox,
                                                   ra_rate, dec_rate]]

            if motion_flag:
                motion_flag = int(motion_flag)
                if motion_flag not in [0, 1, 2]:
                    return {"elaptime": start - time.time(),
                            "error": "Invalid motion flag value"}
                coords.append(motion_flag)

            if epoch:
                coords.append(round(float(epoch), 5))

            if name:
                name = '"%s"' % name
                coords.append(name)
            else:
                name = '"Test"'

            # Check ra
            if coords[0] > 24.0000 or coords[0] < 0:
                return {"elaptime": start - time.time(),
                        "error": "Invalid RA decimal hour"}
            if abs(coords[1]) >= 110:
                return {"elaptime": start - time.time(),
                        "error": "Invalid Dec decimal hour"}
            if coords[2] < 0:
                return {"elaptime": start - time.time(),
                        "error": "Invalid Epoch command"}
            if abs(coords[3]) > 100000:
                return {"elaptime": start - time.time(),
                        "error": "Invalid RA rate"}
            if abs(coords[4]) > 100000:
                return {"elaptime": start - time.time(),
                        "error": "Invalid Dec rate"}
        except Exception as e:
            logger.error("Unable to input coordinates")
            return {"elaptime": start - time.time(),
                    "error": str(e)}
        return self.send_command(cmd="COORDS", parameters=coords)

    def gopos(self):
        """
        GOPOS (SLOW) sends the telescope to the last-specified Target Position
        and tracks that position.  Non-sidereal rates, if any, will be applied,
        and the dome will automatically track the telescope position.  The
        telescope must be initialized (see TELINIT) before this command will
        work.  The command fails if wetness is sensed.  ?POS item Telescope_
        Motion_Status will be SLEWING or MOVING during target acquisition and
        TRACKING upon arrival.

        :return: bool, status message
        """
        return self.send_command(cmd="GOPOS")

    def goref(self):
        """
        GOREF (SLOW) sends the telescope to the last-specified Reference
        Position and tracks that position.  The dome will automatically track
        the telescope position.  The telescope must be initialized
        (see TELINIT) before this command will work.  The command fails if
        wetness is sensed.  ?POS item Telescope_Motion_Status will be SLEWING
        or MOVING during target acquisition and TRACKING upon arrival.

        :return:
        """
        return self.send_command(cmd="GOREF")

    def tel_move_sequence(self, name=None, ra=None, dec=None, equinox=2000,
                          ra_rate=0, dec_rate=0, motion_flag="", epoch=""):

        # 1. Input coordinates
        ret = self.coords(name=name, ra=ra, dec=dec, equinox=equinox,
                          ra_rate=ra_rate, dec_rate=dec_rate,
                          motion_flag=motion_flag, epoch=epoch)

        # 2. If success and this isn't a test move the telescope in positon
        # if we can't input coordinates return error
        if "error" not in ret:
            return self.gopos()
        else:
            return ret

    # INFORMATION COMMANDS
    def list_to_dict(self, list_str):
        """
        Given a list convert it to a dictionary based on a delimiter

        :return: dictionary
        """

        list_str = os.linesep.join([s.lower() for s in list_str.splitlines()
                                    if s and "=" in s])

        if len(list_str) <= 1:
            return False
        return dict(item.split(self.delimiter) for item in list_str.split("\n"))

    def get_weather(self):
        """
        Get the weather output and convert it to a dictionary

        :return: bool, status message
        """
        start = time.time()
        ret = self.send_command("?WEATHER")
        if "data" in ret:
            self.weather = self.list_to_dict(ret['data'])
        else:
            return ret

        return {"elaptime": time.time()-start,
                "data": self.weather}

    def get_status(self, redo=True):
        """
        Get the status output and convert it to a dictionary

        :return: bool, status message
        """

        start = time.time()
        ret = self.send_command("?STATUS")
        if "data" in ret:
            self.status = self.list_to_dict(ret['data'])
        else:
            return ret

        return {"elaptime": time.time() - start,
                "data": self.status}

    def get_pos(self):
        """
        Get the position output and convert it to a dictionary

        :return: bool, status message
        """

        start = time.time()
        ret = self.send_command("?POS")
        if "data" in ret:
            self.pos = self.list_to_dict(ret['data'])
        else:
            return ret
        return {"elaptime": time.time() - start,
                "data": self.pos}

    def get_faults(self):
        """
        Get the faults output and convert it to a dictionary

        :return: bool, status message
        """
        start = time.time()
        ret = self.send_command("?FAULTS")


        if "data" in ret:
            return {"elaptime": time.time() - start,
                    "data": ret['data']}
        else:
            return ret

if __name__ == "__main__":
    x = Telescope()
    print(x.gofocus(15.0))
