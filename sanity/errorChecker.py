import time


class checker:
    def __init__(self, error_search="error"):
        """
        The error checker parses every json formatted dict presented. If the
        error_search variable is in the dict then we decided what to do using
        this class.
        :param error_search:
        """
        self.error_search = error_search

    def check_return(self, return_msg, ):
        """

        :param return_msg:
        :return:
        """

        # 1. First lets make sure that it's the type we want
        start = time.time()
        if not isinstance(return_msg, dict):
            return {'elaptime': time.time()-start,
                    'error': "UNKNOWN return message type"}

        if self.error_search in return_msg:
            # Here is where I will try to diagnosis the error and see what can
            # be done to fix things or determine if the error is critical
            # enough that an automated call should be sent out.
            return {'elaptime': time.time()-start,
                    'error': "ERROR found"}


        else:
            return return_msg
