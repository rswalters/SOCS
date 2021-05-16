import datetime as dt
from dateutil.parser import parse
from skyfield import almanac
from skyfield.api import Topos, load
from skyfield.api import utc
import os
import yaml
import numpy as np


# Open the config file
SR = os.path.abspath(os.path.dirname(__file__) + '/../')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)

eph = load(params['ephem']['load_file'])
palomar = Topos(latitude_degrees=params['ephem']['latitude_degrees'], 
                longitude_degrees=params['ephem']['longitude_degrees'],
                elevation_m=params['ephem']['elevation_m'])

f = almanac.dark_twilight_day(eph, palomar)
d = np.array([4, 3, 2, 1, 0, 1, 2, 3, 4])


def get_science_times(start=None, print_values=False, return_type="dict"):
    """
    Get the science times for the current date or another specified date. All
    input times are assumed to be UT.  Unless otherwise specified we keep the
    geographical location set as Palomar.

    :param print_values:
    :param return_type:
    :param start:3660
    :return:
    """
    # Start out by assuming it's the current date
    next_day = False

    # Figure out the start_time format
    if not start:
        obsdatetime = dt.datetime.utcnow()
    elif isinstance(start, str):
        try:
            obsdatetime = parse(start)
        except Exception as e:
            obsdatetime = dt.datetime.utcnow()
            # print("Invalid night selected")
        # print(obsdatetime)
    elif isinstance(start, dt.datetime):
        obsdatetime = start
    else:
        return {"Na"}

    # If the obsdatetime is past 14:00:00 then we can assume the night is over
    # and go onto the next date.
    if obsdatetime.hour > 14:
        next_day = True

    # Set the start date range to midnight of current obsdatetime
    midnight = obsdatetime.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=utc)

    # Skip to the next day if needed
    if next_day:
        midnight = midnight + dt.timedelta(days=1)

    # Set the end date range to the next midnight
    next_midnight = midnight + dt.timedelta(days=1)

    # Calculate the times for sunset and twilight
    ts = load.timescale()
    t0 = ts.from_datetime(midnight)
    t1 = ts.from_datetime(next_midnight)
    times, events = almanac.find_discrete(t0, t1, f)

    if print_values:
        for t, e in zip(times, d):
            tstr = str(t.utc_strftime())
            print(tstr, ' ', almanac.TWILIGHTS[e], 'starts')

    if return_type == 'dict':
        return {"obs_date": times[2].utc_strftime()[:10],
                "start_science": times[2].utc_strftime()[10:19],
                "end_science": times[5].utc_strftime()[10:19],
                "total_science": round((times[5] - times[2]) * 24, 2)}
    else:
        return times

get_science_times(start=None, print_values=True, return_type="dict")
