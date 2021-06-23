import json
import os
from astropy.io import fits
from astropy import units as u
from astropy.coordinates import SkyCoord


def ra_to_deg(ra):
    """Convert ra in HH:MM:SS.dd format into
    degrees"""
    h, m, s = map(float, ra.split(":"))

    return 15 * h + 0.25 * m + 0.0042 * s


def dec_to_deg(dec):
    """Convert dec in DD:MM:SS.dd format into
    degrees"""
    sign = 1
    d, m, s = map(float, dec.split(":"))
    if d <= 0:
        sign = -1
    return (abs(d) + m / 60. + s / 3600.) * sign


def set_object_coord(coord=-999, coord_type='ra'):
    """
    Determine the input coordinates type and return
    the value in degrees
    :param coord: int, float, or string
    :param coord_type: 'ra' or 'dec'
    :return:
    """
    if isinstance(coord, float):
        return coord
    elif coord and isinstance(coord, str) and ":" not in coord:
        return float(coord)
    elif isinstance(coord, str) and ":" in coord:
        if coord_type.lower() == 'ra':
            return ra_to_deg(coord)
        elif coord_type.lower() == 'dec':
            return dec_to_deg(coord)
    else:
        return -999


class addHeader():
    def __init__(self):

        with open("header.json") as data_file:
            self.header_params = json.load(data_file)
        
        self.tcs_keys = self.header_params['tcs_list']
        self.project_keys = self.header_params['prj_list']
        self.end_keys = self.header_params['end_list']
        self.inst_keys = self.header_params['inst_list']

        # Create a list with all expected keys in the header dict
        self.allkeys = self.tcs_keys+self.project_keys+self.end_keys
        self.allkeys += self.inst_keys

        # Headers values that should be of type of float
        self.float_list = self.header_params['float_list']
        self.default_values = self.header_params['default_dict']

        self.calib_types = ['bias', 'dark', 'dome', 'lamp', 'dome lamp'
                            'twilight', 'darkflat', 'twilightflat']

    def _obsdict_check(self, obsdict):
        """Check for missing objects and that the inputs are in the correct
        format"""
        # Check for missing keys
        missing = set(self.allkeys).difference(obsdict.keys())

        # Put in default values when a key is missing
        for i in missing:
            obsdict[i] = self.default_values[i]

        # Make sure values match type list
        for j in self.float_list:
            try:
                obsdict[j] = float(obsdict[j])
            except Exception as e:
                obsdict[j] = -999.000
                pass
        return obsdict

    def create_default_list(self):
        """Make sure all needed keys have a start value"""
        n = {}
        for i in self.allkeys:
            n[i] = "NA"

    def prep_end_header(self, endStatus):
        """
        Go through and make all adjustments needed to standardize the
        header for SEDm format
        :param ocs_dict:
        :return:
        """
        try:
            end_dict = {'enddome': endStatus['dome_shutter_status'],
                        'end_ra': endStatus['telescope_ra'],
                        'end_dec': endStatus['telescope_dec'],
                        'end_pa': float(endStatus['telescope_parallactic']),
                        'endair': float(endStatus['telescope_airmass']),
                        'endsecpr': float(endStatus['sec_vacuum']),
                        'endbarpr': float(endStatus['bar_pressure']),
                       }
        except Exception as e:
            print(str(e))
            end_dict = {'enddome': "NA",
                        'end_ra':  'NA',
                        'end_dec': 'NA',
                        'end_pa': -999,
                        'endair': -1,
                        'endsecpr': -999,
                        'endbarpr': -999,
                        }
            pass
        return end_dict

    def set_project_keywords(self, test='', imgtype='NA', objtype='NA',
                             object_ra=-999, object_dec=-999, email='',
                             name='', p60prid='NA', p60prpi='SEDm',
                             p60prnm='', obj_id=-999, req_id=-999,
                             objfilter='NA', imgset='NA', is_rc=True,
                             abpair='False'):
        """
        For archiving purposes each observation should have a standard set
        of header fields.

        :param image_type:
        :param test:
        :param imgtype:
        :param marshal_id:
        :param objtype:
        :param object_ra:
        :param object_dec:
        :param email:
        :param name:
        :param p60prid:
        :param p60prpi:
        :param p60prnm:
        :param obj_id:
        :param req_id:
        :return:
        """

        proj_dict = {}

        # Start by setting the object ra and dec keywords
        ra = set_object_coord(object_ra, 'ra')
        dec = set_object_coord(object_dec, 'dec')

        try:
            c = SkyCoord(ra=ra * u.degree, dec=dec * u.degree, frame='icrs')
            coords = c.to_string('hmsdms', sep=':')
            obj_ra, obj_dec = coords.split()
            proj_dict['objra'] = obj_ra
            proj_dict['objdec'] = obj_dec
        except Exception as e:
            proj_dict['objra'] = object_ra
            proj_dict['objdec'] = object_dec

        # Set the name keyword based on image type:
        if imgtype.lower() == 'standard':
            name = "STD-" + name
        elif imgtype.lower() == 'focus':
            name = "FOCUS: " + name
        elif imgtype.lower() == 'acquisition':
            name = "ACQ-" + name
        elif imgtype.lower() == 'guider':
            name = "Guider: " + name
        elif imgtype.lower() in self.calib_types:
            name = "Calib: " + name
        else:
            name = "%s [%s]" % (name, imgset)


        # Set the filter keyword for the rc camera
        #print(objfilter, is_rc)
        if objfilter != 'NA' and is_rc:
            name = name + " %s" % objfilter
            name = name.replace("[%s]" % imgset, "")

        proj_dict['name'] = name.split("[")[0] + test
        proj_dict['object'] = name + test
        proj_dict['imgtype'] = imgtype
        proj_dict['filter'] = objfilter
        # Set all other keywords
        proj_dict['abpair'] = abpair
        proj_dict['imgset'] = imgset
        proj_dict['objtype'] = objtype
        proj_dict['p60prid'] = p60prid
        proj_dict['p60prnm'] = p60prnm
        proj_dict['p60prpi'] = p60prpi
        proj_dict['email'] = email
        proj_dict['req_id'] = req_id
        proj_dict['obj_id'] = obj_id

        return proj_dict

    def set_header(self, image, obsdict):
        """
        Combine a given python dictionary into a fits image header
        :param obsdict:
        :return:
        """
        start = time.time()
        # 1: Start by making sure the image exists
        if os.path.exists(image):
            try:
                hdulist = fits.open(image, mode="update")
                prihdr = hdulist[0].header
            except Exception as e:
                print(str(e))
                return False, str(e)
        else:
            return False, "%s does not exist" % image

        # 2: Check that we have everything we need in the obsdict
        obsdict = self._obsdict_check(obsdict=obsdict)

        prihdr.set("TELESCOP", obsdict["telescope_id"], "Telescope ID")
        prihdr.set("LST", obsdict["lst"], "Local Sideral Time at Start of Observation")
        prihdr.set("MJD_OBS",  float(obsdict['julian_date']) - 2400000.5, "Local Sideral Time at Start of Observation")
        prihdr.set("JD", obsdict["julian_date"], "JD at Start of Observation")
        prihdr.set("APPEQX", obsdict["apparent_equinox"], "Apparent Equinox")
        prihdr.set("EQUINOX", float(obsdict["telescope_equinox"].replace('j', '').replace('b', '')), "Telescope Equinox")
        prihdr.set("TEL_HA", obsdict["telescope_ha"], "Telecope Hour Angle")
        prihdr.set("RA", obsdict["telescope_ra"], "Telescope Ra position start")
        prihdr.set("TEL_RA", obsdict["telescope_ra"], "Telescope Ra position start")
        prihdr.set("DEC", obsdict["telescope_dec"], "Telscope Dec position start ")
        prihdr.set("TEL_DEC", obsdict["telescope_dec"], "Telscope Dec position start ")
        prihdr.set("TEL_AZ", obsdict["telescope_azimuth"], "Telescope Azimuth(degrees)")
        prihdr.set("TEL_EL", obsdict["telescope_elevation"], "Telescope Elevation")
        prihdr.set("AIRMASS", obsdict["telescope_airmass"], "Telescope Airmass")
        prihdr.set("TEL_PA", obsdict["telescope_parallactic"], "Telescope Parallactic Angle")
        prihdr.set("RA_RATE", obsdict["telescope_ra_rate"], "Telescope Ra Rate")
        prihdr.set("DEC_RATE", obsdict["telescope_dec_rate"], "Telescpoe Dec Rate")
        prihdr.set("RA_OFF", obsdict["telescope_ra_offset"], "Telescope RA Offset")
        prihdr.set("DEC_OFF", obsdict["telescope_dec_offset"], "Telescope Dec Offset")
        prihdr.set("TELHASP", obsdict["telescope_ha_speed"], "Telescope HA Speed")
        prihdr.set("TELDECSP", obsdict["telescope_dec_speed"], "Telescope Dec Speed")
        prihdr.set("RA_REFR", obsdict["telescope_ha_refr(arcsec)"], "Telescope RA Refraction")
        prihdr.set("DEC_REFR", obsdict["telescope_dec_refr(arcsec)"], "Telescope Dec Refraction")
        prihdr.set("FOCPOS", obsdict["focus_position"], "Position of secondary focus")
        prihdr.set("IFUFOCUS", obsdict["ifufocus"], "Position of IFU Focus Stage")
        prihdr.set("IFUFOC2", obsdict["ifufoc2"], "Position of RC + IFU Parfocal Stage")
        prihdr.set("DOMEST", obsdict["dome_shutter_status"], "Dome Shutter Status")
        prihdr.set("DOMEMO", obsdict["dome_motion_mode"], "Dome motion mode")
        prihdr.set("DOME_GAP", obsdict["dome_gap(inch)"], "Inches")
        prihdr.set("DOMEAZ", obsdict["dome_azimuth"], "Dome Azimuth(degrees)")
        prihdr.set("WSCRMO", obsdict["ws_motion_mode"], "Windscreen motion mode")
        prihdr.set("TELCONT", obsdict["telescope_control_status"], "Telescope Control Status")
        prihdr.set("LAMPSTAT", obsdict["lamp_status"], "Lamp Status")
        prihdr.set("LAMPCUR", obsdict["lamp_current"], "Lamp Current")
        prihdr.set("HG_LAMP", obsdict["hg_lamp"], "")
        prihdr.set("XE_LAMP", obsdict["xe_lamp"], "")
        prihdr.set("CD_LAMP", obsdict["cd_lamp"], "")
        prihdr.set("TELPOWST", obsdict["telescope_power_status"], "Telescope Power Status")
        prihdr.set("OILSTAT", obsdict["oil_pad_status"], "Oil Pad Status")
        prihdr.set("WEASTAT", obsdict["weather_status"], "Weather Status")
        prihdr.set("SUNSTAT", obsdict["sunlight_status"], "Sunlight Status")
        prihdr.set("REMOTST", obsdict["remote_close_status"], "Remote Close Status")
        prihdr.set("TELRDST", obsdict["telescope_ready_status"], "Telescope Ready Status")
        prihdr.set("HAAX_ST", obsdict["ha_axis_hard_limit_status"], "HA Axis Hard Limit Status")
        prihdr.set("FOCSTAT", obsdict["focus_hard_limit_status"], "Focus Hard Limit Status")
        prihdr.set("DEC_AX", obsdict["dec_axis_hard_limit_status"], "Dec Axis Hard Limit Status")
        prihdr.set("OBJECT", obsdict["object"], "")
        prihdr.set("OBJTYPE", obsdict["objtype"], "")
        prihdr.set("IMGTYPE", obsdict["imgtype"], "")
        prihdr.set("OBJNAME", obsdict["object_name"], "Object name in the TCS")
        prihdr.set("OBJEQX", obsdict["object_equinox"], "Object Coordinate Equinox")
        prihdr.set("OBJRA", obsdict["objra"], "Object's RA")
        prihdr.set("OBJDEC", obsdict["objdec"], "Object's DEC")
        prihdr.set("ORA_RAT", obsdict["object_ra_rate"], "Object Ra Rate")
        prihdr.set("ODEC_RAT", obsdict["object_dec_rate"], "Object Dec Rate")
        prihdr.set("SUNRISE", obsdict["utsunrise"], "UT Sunrise")
        prihdr.set("SUNSET", obsdict["utsunset"], "UT Sunset")
        prihdr.set("TEL_MO", obsdict["telescope_motion_status"], "Telescope Motion Status")
        prihdr.set("WSCR_EL", obsdict["windscreen_elevation"], "Windscreen Elevation")
        prihdr.set("SOL_RA", obsdict["solar_ra"], "Solar RA")
        prihdr.set("SOL_DEC", obsdict["solar_dec"], "Solar Dec")
        prihdr.set("WIND_DIR", obsdict["wind_dir_current"], "Wind direction (degrees)")
        prihdr.set("WSP_CUR", obsdict["windspeed_current"], "Current windspeed (mph)")
        prihdr.set("WSP_AVG", obsdict["windspeed_average"], "Average windspeed (mph)")
        prihdr.set("OUT_AIR", obsdict["outside_air_temp"], "Outside Air Temp")
        prihdr.set("OUT_HUM", obsdict["outside_rel_hum"], "Outside Relative Humidity")
        prihdr.set("OUT_DEW", obsdict["outside_dewpt"], "Outside Dew Point(C)")
        prihdr.set("IN_AIR", obsdict["inside_air_temp"], "Inside Air Temperature(C)")
        prihdr.set("IN_HUM", obsdict["inside_rel_hum"], "Inside Relative Humidity")
        prihdr.set("IN_DEW", obsdict["inside_dewpt"], "Inside Dew Point")
        prihdr.set("MIR_TEMP", obsdict["mirror_temp"], "Primary Temp")
        prihdr.set("TOP_AIR", obsdict["top_air_temp"], "Top Air Temp")
        prihdr.set("PRI_TEMP", obsdict["primary_cell_temp"], "Primary Cell Temp")
        prihdr.set("SEC_TEMP", obsdict["secondary_cell_temp"], "Secondary Cell Temp")
        prihdr.set("FLO_TEMP", obsdict["floor_temp"], "Floor Temp")
        prihdr.set("BOT_TEMP", obsdict["bot_tube_temp"], "Bottom Tube Temp")
        prihdr.set("MID_TEMP", obsdict["mid_tube_temp"], "Mid Tube Temp")
        prihdr.set("TOP_TEMP", obsdict["top_tube_temp"], "Top Tube Temp")
        prihdr.set("WETNESS", obsdict["wetness"], "")
        prihdr.set("FILTER", obsdict["filter"], "Filter Where Object is Located ")
        prihdr.set("ABPAIR", obsdict["abpair"], "Is observation part of AB Pair")
        prihdr.set("IMGSET", obsdict["imgset"], "A or B image")
        prihdr.set("NAME", obsdict["name"], "Science Target Name")
        prihdr.set("P60PRID", obsdict["p60prid"], "Project ID")
        
        prihdr.set("P60PRNM", obsdict["p60prnm"], "Project Name")
        try:
            prihdr.set("P60PRPI", obsdict["p60prpi"], "Project PI")
        except: 
            prihdr.set("P60PRPI", "Default")
            pass
        try:
            prihdr.set("EMAIL", obsdict["email"], "Email")
        except:
            prihdr.set("EMAIL", "rsw@astro.caltech.edu", "Email")
            pass

        prihdr.set("REQ_ID", obsdict["req_id"], "Request Observation ID")
        prihdr.set("OBJ_ID", obsdict["obj_id"], "Database Object ID")

        # TODO: Find out why Nick added this .033 correction
        try:
            #prihdr.set("CRVAL1", round(ra_to_deg('05:23:33') - 0.03333, 5), "Center RA value")
            prihdr.set("CRVAL1", ra_to_deg(obsdict["telescope_ra"]) - 0.03333, "Center RA value")
        except:
            prihdr.set("CRVAL1", -999, "Failed to calculate")
            pass
        try:
            #prihdr.set("CRVAL2", round(dec_to_deg('33:23:33') - 0.03333, 5), "Center Dec value")
            prihdr.set("CRVAL2", dec_to_deg(obsdict["telescope_dec"]) - 0.03333, "Center Dec value")

        except:
            prihdr.set("CRVAL2", -999, "Failed to calculate")

        prihdr.set("BARPRESS", obsdict["bar_pressure"], "Atmosphere Pressure")
        prihdr.set("SECPRESS", obsdict["sec_vacuum"], "Secondary Vacuum Pressure")
        prihdr.set("ENDAIR", obsdict["endair"], "Airmass at shutter close")
        prihdr.set("ENDDOME", obsdict["enddome"], "Dome state at shutter close")
        prihdr.set("END_RA", obsdict["end_ra"], "Telescope RA at shutter close")
        prihdr.set("END_DEC", obsdict["end_dec"], "Telescope DEC at shutter close")
        prihdr.set("END_PA", obsdict["end_pa"], "Telescope PA at shutter close")
        prihdr.set("ENDBARPR", obsdict["endbarpr"], "End Atmosphere Pressure")
        prihdr.set("ENDSECPR", obsdict["endsecpr"], "End Secondary Vacuum Pressure")
        prihdr.set("ELAPTIME",  round(time.time() - obsdict['starttime'], 3), "Elapsed time of observation")
        hdulist.close()

        return {'elaptime': time.time()-start, 'data': image}

if __name__ == "__main__":
    x = addHeader()
    y = {'utc': '2019:245:12:13:02.2', 'telescope_id': '60', 'telescope_control_status': 'remote', 'lamp_status': 'off', 'lamp_current': '0.00', 'dome_shutter_status': 'closed', 'ws_motion_mode': 'bottom', 'dome_motion_mode': 'anticipate', 'telescope_power_status': 'ready', 'oil_pad_status': 'ready', 'weather_status': 'ready', 'sunlight_status': 'okay', 'remote_close_status': 'not_okay', 'telescope_ready_status': 'ready', 'ha_axis_hard_limit_status': 'okay', 'dec_axis_hard_limit_status': 'okay', 'focus_hard_limit_status': 'okay', 'focus_soft_up_limit_value': '35.00', 'focus_soft_down_limit_value': '0.50', 'focus_soft_limit_status': 'okay', 'focus_motion_status': 'stationary', 'east_soft_limit_value': '-6.4', 'west_soft_limit_value': '6.4', 'north_soft_limit_value': '109.5', 'south_soft_limit_value': '-41.8', 'horizon_soft_limit_value': '10.0', 'ha_axis_soft_limit_status': 'okay', 'dec_axis_soft_limit_status': 'okay', 'horizon_soft_limit_status': 'okay', 'windspeed_avg_threshold': '25.0', 'gust_speed_threshold': '35.0', 'gust_hold_time': '900', 'outside_dewpt_threshold': '2.0', 'inside_dewpt_threshold': '2.0', 'wetness_threshold': '500', 'wind_dir_current': '63', 'windspeed_current': '3.7', 'windspeed_average': '5.7', 'outside_air_temp': '20.5', 'outside_rel_hum': '65.7', 'outside_dewpt': '13.9', 'inside_air_temp': '21.3', 'inside_rel_hum': '55.9', 'inside_dewpt': '12.1', 'mirror_temp': '21.2', 'floor_temp': '21.7', 'bot_tube_temp': '21.0', 'mid_tube_temp': '21.3', 'top_tube_temp': '21.4', 'top_air_temp': '21.3', 'primary_cell_temp': '21.2', 'secondary_cell_temp': '21.2', 'wetness': '-271', 'lst': '03:11:01.3', 'julian_date': '2458729.0090534', 'apparent_equinox': '2019.67', 'telescope_equinox': 'j2000.0', 'telescope_ha': 'e00:51:28.85', 'telescope_ra': '04:01:38.90', 'telescope_dec': '-20:31:56.3', 'telescope_ra_rate': '0.00', 'telescope_dec_rate': '0.00', 'telescope_ra_offset': '13166.08', 'telescope_dec_offset': '-110.87', 'telescope_azimuth': '165.34', 'telescope_elevation': '34.84', 'telescope_parallactic': '347', 'telescope_ha_speed': '-0.0046', 'telescope_dec_speed': '0.0000', 'telescope_ha_refr(arcsec)': '-15.25', 'telescope_dec_refr(arcsec)': '-65.88', 'telescope_motion_status': 'stopped', 'telescope_airmass': '1.747', 'telescope_ref_ut': '11.840406', 'object_name': '"simulated"', 'object_equinox': 'j2000.0', 'object_ra': '03:46:01.55', 'object_dec': '-20:30:27.9', 'object_ra_rate': '0.00', 'object_dec_rate': '0.00', 'object_ra_proper_motion': '0.000000', 'object_dec_proper_motion': '0.00000', 'focus_position': '15.81', 'dome_gap(inch)': '-240', 'dome_azimuth': '233.3', 'windscreen_elevation': '0', 'utsunset': '02:31', 'utsunrise': '13:00', 'solar_ra': '10:44', 'solar_dec': '+07:58'}
    #x._obsdict_check(y)
    import time
    s = time.time()
    print(x.set_header('/home/rsw/images/20190906/rc20190906_20_25_42.fits', y))
    print(time.time()-s)
