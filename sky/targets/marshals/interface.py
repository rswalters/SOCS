import os
import glob
import requests
import time
import json
import yaml


SR = os.path.abspath(os.path.dirname(__file__) + '/../../../')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)


def api(method, endpoint, data=None, json_file=None, marshal_id=0):
    """
    Act as
    :param json_file:
    :param method:
    :param endpoint:
    :param data:
    :param marshal_id:
    :return:

    """

    if marshal_id >= 1:
        headers = {'Authorization': 'token {}'.format(params['marshals']['fritz']['token'])}
        response = requests.request(method, endpoint, json=data,
                                    headers=headers)
    else:
        response = requests.post(endpoint,
                                 files={'jsonfile': json_file},
                                 auth=(params['marshals']['growth']['user'],
                                 params['marshals']['growth']['password']))

    print('HTTP code: {}, {}'.format(response.status_code, response.reason))
    if response.status_code in (200, 400):
        print(response.text)

    return response


def get_marshal_id_from_pharos(request_id):
    """
    Get the marshal id from the pharos website

    :param request_id:
    :return:
    """
    start = time.time()
    payload = {'request_id': request_id}
    headers = {'content-type': 'application/json'}
    json_data = json.dumps(payload)
    response = requests.post(params['marshal']['pharos'], data=json_data,
                             headers=headers)
    ret = json.loads(response.text)

    if 'error' in ret:
        return {'elaptime': time.time() - start,
                'error': 'Error getting the growth id'}
    else:
        return {'elaptime': time.time() - start,
                'data': ret['marshal_id']}


def update_status_request(status, request_id, marshal_name, save=False,
                          output_file='', testing=False):
    """
    Function to update the status of any request as long as it has
    not been deleted. The new status will show up on the status section
    of the request on the growth marshal.

    :param status: string with new update status
    :param request_id: request id in the pharos database
    :param marshal_name: string with marshal endpoint
    :param save: save the update json file
    :param output_file: file name if save is true
    :param testing: only print out request and not send to external marshal
    :return: dict with elapsed time and http status return
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
                  data=status_payload, json_file=output_file).json()
        if 'success' in ret['status']:
            print('Status for request %d updated to %s' % (request_id, status))
        else:
            print('Status update failed:\n', ret)
            if "message" in ret:
                ret["iserror"] = ret['message']
            else:
                ret["iserror"] = "Unkown error when posting update"
        return ret