import socket
import time
import json


class Sky:

    def __init__(self, address='localhost', port=5004, timeout=300):
        """

        :param camera:
        :param address:
        :param port:
        """

        self.address = address
        self.port = port
        self.default_timeout = timeout
        self.timeout = timeout
        print(self.address, self.port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.address, self.port))

    def __send_command(self, cmd="", parameters=None, timeout=180,
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

                self.socket.settimeout(self.timeout)
                self.timeout = self.default_timeout

            if parameters:
                send_str = json.dumps({'command': cmd,
                                       'parameters': parameters})
            else:
                send_str = json.dumps({'command': cmd})

            self.socket.send(b"%s" % send_str.encode('utf-8'))

            if return_before_done:

                return {"elaptime": time.time()-start,
                        "command": cmd,
                        "data": "exiting the loop early"}

            data = self.socket.recv(2048)
            counter = 0
            while not data:
                time.sleep(.1)
                data = self.socket.recv(2048)
                counter += 1
                if counter > 100:
                    break

            ret_dict = json.loads(data.decode('utf-8'))
            if isinstance(ret_dict, dict):
                if 'command' not in ret_dict:
                    ret_dict['command'] = cmd
                return ret_dict
        except Exception as e:
            return {'elaptime': time.time() - start, 'error': str(e)}

    def solve_offset_new(self, raw_image, overwrite=True,
                         parse_directory_from_file=False,
                         return_before_done=False,
                         base_dir='/data2/sedm/'):
        parameters = {
            'raw_image': raw_image, 'overwrite': overwrite,
            'parse_directory_from_file': parse_directory_from_file,
            'base_dir': base_dir

        }

        return self.__send_command(cmd="GETOFFSETS",
                                   return_before_done=return_before_done,
                                   parameters=parameters)

    def check_socket(self):
        """
        Try sending a command to the camera program
        :return:(bool,response)
        """
        return self.__send_command(cmd="PING")

    def reinit(self):
        """
        Try sending a command to the camera program
        :return:(bool,response)
        """
        return self.__send_command(cmd='REINT')

    def start_guider(self, start_time=None, end_time=None, exptime=30,
                     image_prefix="rc", max_move=None, min_move=None,
                     data_dir=None, debug=False, wait_time=5,
                     return_before_done=True):
        """
        :param return_before_done:
        :param start_time:
        :param end_time:
        :param exptime:
        :param image_prefix:
        :param max_move:
        :param min_move:
        :param data_dir:
        :param debug:
        :param wait_time:
        :return:
        """
        parameters = dict(start_time=start_time, end_time=end_time,
                          exptime=exptime, image_prefix=image_prefix,
                          max_move=max_move, min_move=min_move,
                          data_dir=data_dir, debug=debug, wait_time=wait_time)

        return self.__send_command(cmd="STARTGUIDER",
                                   parameters=parameters,
                                   return_before_done=return_before_done)

    def get_standard(self, name="zenith", obsdate=""):
        """

        :param name:
        :param ra:
        :param dec:
        :param obsdate:
        :return:
        """

        parameters = {
            "name": name,
            "obsdate": obsdate
        }

        return self.__send_command(cmd="GETSTANDARD",
                                   parameters=parameters)

    def get_next_observable_target(self, target_list=None, obsdatetime=None,
                                   airmass=(1, 2.5), moon_sep=(30, 180),
                                   altitude_min=15, ha=(18.75, 5.75),
                                   return_type='json',
                                   do_sort=True,
                                   sort_columns=('priority', 'start_alt'),
                                   sort_order=(False, False), save=True,
                                   save_as='',
                                   check_end_of_night=True, update_coords=True):
        parameters = {
            'target_list': target_list,
            'obsdatetime': obsdatetime,
            'airmass': airmass,
            'moon_sep': moon_sep,
            'altitude_min': altitude_min,
            'ha': ha,
            'return_type': return_type,
            'do_sort': do_sort,
            'sort_columns': sort_columns,
            'sort_order': sort_order,
            'save': save,
            'save_as': save_as,
            'check_end_of_night': check_end_of_night,
            'update_coords': update_coords
        }

        return self.__send_command(cmd="GETTARGET",
                                   parameters=parameters)

    def get_best_focus(self, files, ifu=False):
        parameters = {
            'files': files,
            'ifu': ifu
        }
        ret, focus = self.__send_command(cmd="GETBESTFOCUS",
                                         parameters=parameters)

        try:
            x = json.loads(focus)
        except Exception as e:
            print(str(e))
            print("Error above")
            x = ''
        return ret, x

    def get_focus(self, obs_list, header_field='FOCPOS',
                  overwrite=False,
                  catalog_field='FWHM_IMAGE',
                  filter_catalog=True):

        parameters = {
            'obs_list': obs_list,
            'header_field': header_field,
            'overwrite': overwrite,
            'catalog_field': catalog_field,
            'filter_catalog': filter_catalog
        }
        return self.__send_command(cmd="GETRCFOCUS",
                                   parameters=parameters)

    def get_standard_request_id(self, name="", exptime=90):
        parameters = {
            'name': name,
            'exptime': exptime
        }
        return self.__send_command(cmd="GETSTANDARDREQUESTID",
                                       parameters=parameters)

    def get_calib_request_id(self, camera='ifu', N=1, object_id="",
                             exptime=0):
        parameters = {
            'camera': camera,
            'N': N,
            'object_id': object_id,
            'exptime': exptime
        }
        return self.__send_command(cmd="GETCALIBREQUESTID",
                                   parameters=parameters)

    def update_growth(self, growth_id=None, request_id=None,
                      message="PENDING"):
        """

        :param growth_id:
        :param request_id:
        :param message:
        :return:
        """
        parameters = {
            'growth_id': growth_id,
            'request_id': request_id,
            'message': message
        }

        return self.__send_command(cmd="UPDATEGROWTH",
                                   parameters=parameters)

    def update_target_request(self, request_id, status="COMPLETED"):

        parameters = {
            'request_id': request_id,
            'status': status
        }
        return self.__send_command(cmd="UPDATEREQUEST",
                                   parameters=parameters)

    def get_focus_coords(self, obsdatetime="", dec=33.33):
        parameters = {
            'obsdatetime': obsdatetime,
            'dec': dec
        }

        return self.__send_command(cmd="GETFOCUSCOORDS",
                                   parameters=parameters)

    def get_twilight_coords(self, obsdatetime="", dec=33.33):
        parameters = {
            'obsdatetime': obsdatetime,
            'dec': dec
        }
        return self.__send_command(cmd="GETTWILIGHTCOORDS",
                                   parameters=parameters)

    def get_twilight_exptime(self, obsdatetime=""):
        parameters = {
            'obsdatetime': obsdatetime
        }

        return self.__send_command(cmd="GETTWILIGHTEXPTIME",
                                   parameters=parameters)

    def wait_for_solution(self, abpair=True):
        parameters = {
            'abpair': abpair
        }
        ret, offsets = self.__send_command(cmd="WAITFOROFFSETS",
                                           parameters=parameters)
        return ret, offsets

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
    print(rc.get_next_observable_target(return_type='json'))
    print(time.time()-s)
