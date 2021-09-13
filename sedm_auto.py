from sedm import SEDm
from utils import obstimes
import datetime
import time
from astropy.time import Time
from twilio.rest import Client
import os


common_file_dir = "common_files"

manual_file = os.path.join(os.path.join(common_file_dir, "manual.json"))
calib_done_file = os.path.join(os.path.join(common_file_dir, "calib_done.txt"))
focus_done_file = os.path.join(os.path.join(common_file_dir, "focus_done.txt"))
standard_done_file = os.path.join(os.path.join(common_file_dir,
                                               "standard_done.txt"))
run_focus_file = os.path.join(os.path.join(common_file_dir, "do_focus.txt"))
run_standard_file = os.path.join(os.path.join(common_file_dir,
                                              "do_standard.txt"))

comm_files = [calib_done_file, focus_done_file, standard_done_file,
              run_standard_file, run_focus_file]

for i in comm_files:
    print(i, os.path.exists(i))


def make_alert_call():
    account_sid = 'AC8011a27c5e9acbe07fe8d843fda38999'
    auth_token = '32e7f462e91d7fd972ab58cfd8a63272'

    client = Client(account_sid, auth_token)

    call = client.calls.create(url='http://demo.twilio.com/docs/voice.xml',
                               to='+16265673112', from_='+17602923391')

    print(call.sid)


def uttime(offset=0):
    if not offset:
        return Time(datetime.datetime.utcnow())
    else:
        return Time(datetime.datetime.utcnow() +
                    datetime.timedelta(seconds=offset))


def clean_up():
    print("Cleaning up")
    for ic in [calib_done_file, focus_done_file,
               standard_done_file, run_focus_file,
               run_standard_file]:

        if os.path.exists(ic):
            os.remove(ic)


def run_observing_loop(  # do_focus=True, do_standard=True,
                       do_calib=True):

    if os.path.exists(focus_done_file):
        focus_done = True
    else:
        focus_done = False

    if os.path.exists(standard_done_file):
        standard_done = True
    else:
        standard_done = False

    if os.path.exists(calib_done_file):
        calib_done = True
    else:
        calib_done = False

    done_list = []

    count = 1

    robot = SEDm()
    robot.initialize()
    ntimes = obstimes.ScheduleNight()
    night_obs_times = ntimes.get_observing_times_by_date()

    for k, v in night_obs_times.items():
        print(k, v.iso)

    if datetime.datetime.utcnow().hour >= 14:
        print("Waiting fot calibs")
        while datetime.datetime.utcnow().hour != 0:
            time.sleep(60)

    if not calib_done and do_calib:
        if not os.path.exists(calib_done_file):
            # ret = robot.take_datacube_eff()
            ret = robot.take_datacube(robot.ifu, cube='ifu', move=True)
            ret1 = robot.take_datacube(robot.rc, cube='rc', move=True)
            print(ret, ret1)
            with open(calib_done_file, 'w') as the_file:
                the_file.write('Datacube completed:%s' % uttime())
    night_obs_times = ntimes.get_observing_times_by_date()
    for k, v in night_obs_times.items():
        print(k, v.iso)
    print("Waiting for civil twilight to open dome")
    while uttime() < night_obs_times['evening_civil']:
        time.sleep(60)

#   while not robot.conditions_cleared():
#       if uttime() > night_obs_times['morning_nautical']:
#           break
#       print("Weather/P200 fault")
#       time.sleep(60)

    while uttime() < night_obs_times['evening_nautical']:
        robot.check_dome_status()
        max_time = (night_obs_times['evening_nautical'] -
                    Time(datetime.datetime.utcnow())).sec
        print(max_time, "Time to do flats")
        robot.take_twilight(robot.rc, max_time=max_time,
                            end_time=night_obs_times['evening_nautical'])
        time.sleep(60)

    print("Waiting for nautical twilight")
#   while not robot.conditions_cleared():
#      if uttime() > night_obs_times['morning_nautical']:
#            break
#      print("Weather/P200 fault")
#      time.sleep(60)

    while uttime() < night_obs_times['evening_nautical']:

        time.sleep(5)
    
    print(datetime.datetime.utcnow(), 'current_time')
    print(night_obs_times['morning_nautical'].iso, 'close_time')

    while uttime() < night_obs_times['morning_nautical']:
        while robot.conditions_cleared() is not None:
            print(robot.conditions_cleared(), 22222)
            if uttime() > night_obs_times['morning_nautical']:
                break
            print("Weather/P200 fault")
       
            time.sleep(60)
        print(robot.conditions_cleared(), 'test')
        if uttime() > night_obs_times['morning_nautical']:
            break
        else:
            print(robot.check_dome_status())

        if not focus_done:
            print("Doing focus")
            ret = robot.run_focus_seq(robot.rc, 'rc_focus', name="Focus")
            print(ret)
            # robot.ocs.goto_focus(pos=16.23)
            with open(focus_done_file, 'w') as the_file:
                the_file.write('Focus completed:%s' % uttime())
            focus_done = True

        if not standard_done:
            print("Doing standard")
            ret = robot.run_standard_seq(robot.ifu)
            print(ret)

            with open(standard_done_file, 'w') as the_file:
                the_file.write('Standard completed:%s' % uttime())

            standard_done = True

        if os.path.exists("manual.json"):
            print(robot.run_manual_command('manual.json'))
            os.remove("manual.json")

        try:
            ret = robot.sky.get_next_observable_target(return_type='json')
            print(ret)
        except Exception as ex:
            print(str(ex), "ERROR getting target")
            ret = robot.sky.reinit()
            print(ret, "error 1")
            time.sleep(10)
            ret = robot.sky.reinit()
            print(ret, "error2")
            ret = None
            pass

        if not ret:
            ret = robot.sky.get_next_observable_target(return_type='json')

        if 'data' in ret:
            obsdict = ret['data']
            if obsdict['req_id'] in done_list:
                robot.sky.update_target_request(obsdict['req_id'],
                                                status='COMPLETED')
                continue
            end_time = datetime.datetime.utcnow() + datetime.timedelta(
                seconds=obsdict['obs_dict']['total'])
            if Time(end_time) > night_obs_times['morning_nautical']:
                print("Waiting to close dome")
                print("Doing standard")
                ret = robot.run_standard_seq(robot.ifu)
                print(ret)
                time.sleep(600)
                continue
            ret = robot.observe_by_dict(obsdict)
            done_list.append(obsdict['req_id'])
            
            print(ret)
            # Removing the focus done file will now make sure the system
            # refocuses during the night
            if not os.path.exists(focus_done_file):
                _ = robot.run_focus_seq(robot.rc, 'rc_focus', name="Focus")
                with open(focus_done_file, 'w') as the_file:
                    the_file.write('Focus completed:%s' % uttime())

        else:
            print("No return value")
            _ = robot.run_standard_seq(robot.ifu)
        print("I am in the loop", count)
        count += 1

    print("End of the night")

    ret = robot.ocs.dome('close')
    print(ret)
    time.sleep(120)
    ret = robot.ocs.stow(ha=0, dec=109, domeaz=220)
    print(ret)

    print("Cleaning up")
    clean_up()
    ret = robot.ocs.stow(ha=0, dec=109, domeaz=220)
    print(ret)
    print("Going to sleep")
    time.sleep(7200)
    print("Second sleep")
    time.sleep(7200)
    print("Third")
    time.sleep(7200)


if __name__ == "__main__":
    try:
        while True:
            try:
                run_observing_loop()
            except Exception as e:
                print(str(e))
                time.sleep(60)
                pass

    except Exception as e:
        print(str(e))
