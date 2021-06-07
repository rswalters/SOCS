import os
import glob
import requests
import time
import json


def get_marshal_id_from_pharos(request_id):
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
        return {'elaptime': time.time() - start,
                'error': 'Error getting the growth id'}
    else:
        return {'elaptime': time.time() - start,
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
        return {"elaptime": time.time() - start,
                "error": "No growth id or request id given"}

    if not growth_id and request_id:
        ret = self.get_marshal_id_from_pharos(request_id)
        if 'error' in ret:
            return ret
        else:
            growth_id = ret['data']

    if not growth_id or not isinstance(growth_id, int):
        return {'elaptime': time.time() - start,
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

    return {'elaptime': time.time() - start,
            'data': ret.status_code}


def api(method, endpoint, data=None):
    headers = {'Authorization': 'token {}'.format(token)}
    response = requests.request(method, endpoint, json=data, headers=headers)
    print('HTTP code: {}, {}'.format(response.status_code, response.reason))
    if response.status_code in (200, 400):
        print(response.text)
        #print('JSON response: {}'.format(response.json()))

    return response


def update_status_request(status, request_id, marshal_name, save=False,
                          output_file='', testing=False):
    """
    Function to update the status of any request as long as it has
    not been deleted. The new status will show up on the status section
    of the request on the growth marshal.

    :param status:
    :param request_id:
    :param marshal_name:
    :param save:
    :param output_file:
    :param testing:
    :return:
    """

    # 1. Get the instrument id
    if marshal_name.lower() not in params['marshals']:
        return {"iserror": True, "msg": "Marshal: %s not found in config file"}

    if save:
        if not output_file:
            request_str = str(request_id)
            output_file = os.path.join(marshal_name.lower(), "_", request_str,
                                       ".json")

            if os.path.exists(output_file):
                files = sorted(glob.glob("*_%s_*"))
                if not files:
                    output_file = os.path.join(marshal_name.lower(), "_",
                                               request_str, "_", "1", ".json")
                else:
                    last_file_count = files[-1].split('_')[-1].replace('.json',
                                                                       '')
                    last_file_count = int(last_file_count) + 1
                    output_file = os.path.join(marshal_name.lower(), "_",
                                               request_str, "_",
                                               str(last_file_count),
                                               ".json")
        print("output_file(not used) = %s" % output_file)

    # 2. Create the new status dictionaryCopy
    status_payload = {
        "new_status": status,
        "followup_request_id": request_id
    }

    # 3. Send the update
    if testing:
        print(status_payload)
    else:
        ret = api("POST", params["marshals"][marshal_name]['status_url'],
                  data=status_payload).json()
        if 'success' in ret['status']:
            print('Status for request %d updated to %s' % (request_id, status))
        else:
            print('Status update failed:\n', ret)
            if "message" in ret:
                ret["iserror"] = ret['message']
            else:
                ret["iserror"] = "Unkown error when posting update"
        return ret