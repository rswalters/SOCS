import glob
import os
import time
from astropy.io import fits


class Checker:
    def __init__(self, data_dir='/home/sedm/images/'):
        self.data_dir = data_dir

    def check_for_images(self, camera, keywords,
                         time_cut=None, data_dir=None):
        """

        :param camera:
        :param keywords:
        :return:
        """
        start = time.time()
        img_list = []
        files = []
        if not data_dir:
            data_dir = self.data_dir

        # 1. Get the images
        if isinstance(data_dir, list):
            for i in data_dir:
                path = os.path.join(i, camera+"*.fits")
                print("Checking %s" % path)
                files += glob.glob(path)
        else:
            path = os.path.join(data_dir, camera + "*.fits")
            print("Checking %s" % path)
            files += glob.glob(path)

        if not isinstance(keywords, dict):
            return {'elaptime': time.time()-start,
                    'error': "keywords are not in dict form"}

        for f in files:
            add = False
            header = fits.getheader(f)
            for k, v in keywords.items():
                if k.upper() in header:
                    if isinstance(v, str):
                        if v.lower() in header[k.upper()]:
                            add = True
                        else:
                            add = False
                    elif isinstance(v, float) or isinstance(v, int):
                        if v == header[k.upper()]:
                            add = True
                        else:
                            add = False
                else:
                    print("Header %s not found" % k.upper())
                    add = False

            if add:
                img_list.append(f)

        return {'elaptime': time.time()-start, 'data': img_list}

if __name__ == "__main__":
    x = Checker()
    ret = x.check_for_images('ifu', keywords={'object': 'bias', 'ADCSPEED': 2.0},
                       data_dir='/home/sedm/images/20191125')
    print(len(ret['data']))