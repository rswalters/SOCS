import time
import json


def send_message(outgoing_connection, cmd="", parameters=None, timeout=300,
                 return_before_done=False, start=0):
    """
    Any command sent to the server should expect a json string return

    :param start: Unix timestamp float
    :param outgoing_connection:
    :param return_before_done:
    :param cmd: string command to send to the camera socket
    :param parameters: list of parameters associated with cmd
    :param timeout: timeout in seconds for waiting for a command
    :return: Tuple (bool,string)
    """

    try:
        # 1. Set a time out for the connection if needed
        if timeout:
            outgoing_connection.settimeout(timeout)

        # 2. Convert the command and parameters into a json string
        if parameters:
            send_str = json.dumps({'command': cmd,
                                   'parameters': parameters})
        else:
            send_str = json.dumps({'command': cmd})

        # 3. Send the command to the intended server
        outgoing_connection.send(b"%s" % send_str.encode('utf-8'))

        # 4.
        if return_before_done:
            return {"elaptime": time.time() - start,
                    "data": "exiting the loop early"}

        data = outgoing_connection.recv(2048)
        counter = 0
        while not data:
            time.sleep(.01)
            data = outgoing_connection.recv(2048)
            counter += 1
            if counter > 100:
                break
        return json.loads(data.decode('utf-8'))

    except Exception as e:
        return {'elaptime': time.time() - start,
                'error': str(e)}