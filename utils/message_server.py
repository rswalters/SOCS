import json
import time


def error_handler(msg, starttime=0.0, inputdata=None, return_type='json',
                  incoming_connection=None):
    """

    :param incoming_connection:
    :param msg:
    :param starttime:
    :param inputdata:
    :param return_type:
    :return:
    """

    if return_type == 'json':
        return json.dumps({"elaptime": time.time() - starttime,
                           "input": inputdata,
                           "error": "error message %s" % msg})


def response_handler(msg, starttime=0.0, inputdata=None, return_type='json',
                     incoming_connection=None):
    """

    :param incoming_connection:
    :param msg:
    :param starttime:
    :param inputdata:
    :param return_type:
    :return:
    """
    if isinstance(msg, dict):
        if 'data' in msg:
            msg = msg['data']
        elif 'error' in msg:
            return error_handler(msg, starttime=starttime,
                                 inputdata=inputdata,
                                 return_type=return_type)

    if return_type == 'json':
        return json.dumps({"elaptime": time.time() - starttime,
                           "input": inputdata,
                           "data": msg})
    else:
        return True


def message_handler(incoming_connection, starttime=0.0):
    """

    :param incoming_connection:
    :param starttime:
    :return:
    """

    # 1. Start by parsing the incoming request
    try:
        data = incoming_connection.recv(2048)
        data = data.decode("utf8")
    except Exception as e:
        print("Unable to retrieve incoming data")
        error_dict = error_handler("Unable to retrieve and decode "
                                   "incoming data: %s" % str(e),
                                   starttime=starttime,
                                   inputdata='NA',
                                   return_type='json')
        # Send reply back to incoming address and exit the loop

        incoming_connection.sendall(error_dict)
        return False

    # 2. Verify that the incoming command has valid data
    if not data:
        error_dict = error_handler("No data was received",
                                   starttime=starttime,
                                   inputdata='NA')

        #incoming_connection.sendall(error_dict)
        return False

    # 3. Now check that the data is in the proper format with a command
    # key and optional parameters
    try:
        data = json.loads(data)
    except Exception as e:
        print(str(e))
        print("Unable to load the incoming json request")
        # logger.error("Load error", exc_info=True)
        error_dict = error_handler("Unable to load the incoming json "
                                   "request: %s" % str(e),
                                   starttime=starttime,
                                   inputdata=data,
                                   return_type='json')
        # Send reply back to incoming address and exit the loop
        incoming_connection.sendall(error_dict.encode('utf-8'))
        return False

    # 4. Check that we have an incoming command
    if 'command' not in data:
        error_dict = error_handler("'command' not in input data",
                                   starttime=starttime, inputdata=data,
                                   return_type='json')
        # Send reply back to incoming address and exit the loop
        incoming_connection.sendall(error_dict.encode('utf-8'))
        return False

    return data

