import json
import requests
import time


class interface:
    def __init__(self, pharos_get_url="http://pharos.caltech.edu/get_marshal_id",
                 growth_url="http://skipper.caltech.edu:8080/cgi-bin/growth/update_followup_status.cgi",
                 instrument_id=65, user="", passwd=""):
        """

        :param pharos_get_url:
        :param growth_url:
        :param instrument_id:
        :param user:
        :param passwd:
        """

        self.pharos_url = pharos_get_url
        self.growth_url = growth_url
        self.instrument_id = instrument_id
        self.user = user
        self.passwd = passwd

    def get_marshal_id_from_pharos(self, request_id):
        """

        :param request_id:
        :return:
        """
        start = time.time()
        payload = {'request_id': request_id}
        headers = {'content-type': 'application/json'}
        json_data = json.dumps(payload)
        response = requests.post(self.pharos_url, data=json_data,
                                 headers=headers)
        ret = json.loads(response.text)
        if 'error' in ret:
            return {'elaptime': time.time()-start,
                    'error': 'Error getting the growth id'}
        else:
            return {'elaptime': time.time()-start,
                    'data': ret['marshal_id']}

    def update_growth_status(self, growth_id=None, request_id=None,
                             message="PENDING"):
        """

        :param growth_id:
        :param request_id:
        :param message:
        :return:
        """
        start = time.time()
        if not growth_id and not request_id:
            return {"elaptime": time.time()-start,
                    "error": "No growth id or request id given"}

        if not growth_id and request_id:
            ret = self.get_marshal_id_from_pharos(request_id)
            if 'error' in ret:
                return ret
            else:
                growth_id = ret['data']

        if not growth_id or not isinstance(growth_id, int):
            return {'elaptime': time.time()-start,
                    'error': growth_id}

        # If we make it to this step then we should have a valid growth marshal target

        status_config = {
            'instrument_id': self.instrument_id,
            'request_id': growth_id,
            'new_status': message
        }

        out_file = open('json_file.txt', 'w')
        out_file.write(json.dumps(status_config))
        out_file.close()

        json_file = open('json_file.txt', 'r')

        ret = requests.post(self.growth_url, auth=(self.user, self.passwd),
                            files={'jsonfile': json_file})

        json_file.close()

        return {'elaptime': time.time()-start,
                'data': ret.status_code}

