import datetime
import os
import glob
import time
from astropy.io import ascii
from sky.astrometry.sextractor import run
from scipy.spatial.distance import cdist
import numpy as np
import socket
import pandas as pd
from photutils import centroid_sources, centroid_2dg
from astropy.io import fits

class Guide:
    def __init__(self, config_file='', data_dir='images/',
                 max_move=1, min_move=.05, ip="10.200.100.2",
                 do_connect=False, port=49300):
        """

        :param config_file:
        :param data_dir:
        :param max_move:
        :param min_move:
        """

        self.config_file = config_file
        self.data_dir = data_dir
        self.max_move = max_move
        self.min_move = min_move
        self.extractor = run.Sextractor()
        self.telescope_ip = ip
        self.telescope_port = port
        self.ocs = None #ocs_client.Observatory()
        self.socket = socket.socket()
        self.do_connect = do_connect
        if self.do_connect:
            self.socket.connect((self.telescope_ip, self.telescope_port))

    def _get_catalog_positions(self, catalog, do_filter=True,
                               ellip_constraint=.2):

        # Read in the sextractor catalog and convert to dataframe
        if catalog[-4:] == 'fits':
            ret = self.extractor.run(catalog)
            #print(ret)
            if 'data' in ret:
                catalog = ret['data']

        data = ascii.read(catalog)

        df = data.to_pandas()

        if do_filter:
            df = df[(df['X_IMAGE'] > 50) & (df['X_IMAGE']) < 2000]
            print(df, '12')
            df = df[(df['X_IMAGE'] < 850) | (df['X_IMAGE'] > 1250)]
            print(df, '13')
            df = df[(df['Y_IMAGE'] > 50) & (df['Y_IMAGE']) < 2000]
            print(df, '14')
            df = df[(df['Y_IMAGE'] < 800) | (df['Y_IMAGE'] > 1250)]
            print(df, '15')
            df = df[(df['FLAGS'] == 0) & (df['ELLIPTICITY'] < ellip_constraint)]

            df = df.sort_values(by=['MAG_BEST'])
            df = df[0:5]

        return df

    def _closest_point(self, point, points):
        """ Find closest point from a list of points. """
        return points[cdist([point], points).argmin()]

    def _reject_outliers(self, data, m=.5):
        return data[abs(data - np.mean(data)) < m * np.std(data)]

    def detect_outlier(self, data_x, data_y, return_index=False):
        outliers_x = []
        outliers_y = []
        threshold = 1.5

        # start with x rejection points
        mean_x = np.mean(data_x)
        std_x = np.std(data_x)

        for i in range(len(data_x)):
            z_score = (data_x[i] - mean_x) / std_x

            if np.abs(z_score) > threshold:

                outliers_x.append(i)

        # now y
        mean_y = np.mean(data_y)
        std_y = np.std(data_y)
        for i in range(len(data_y)):
            z_score = (data_y[i] - mean_y) / std_y
            if np.abs(z_score) > threshold:

                outliers_y.append(i)

        # now remove x points from both arrays
        remove_indexes = outliers_x + list(set(outliers_y) - set(outliers_x))

        if return_index:
            return remove_indexes

        for index in sorted(remove_indexes, reverse=True):
            data_x = np.delete(data_x, index)
            data_y = np.delete(data_y, index)

        return [data_x, data_y]

    def generate_region_file(self, catalog):
        """

        :param catalog:
        :return:
        """

        if isinstance(catalog, str):
            df = self._get_catalog_positions(catalog)
        elif isinstance(catalog, pd.DataFrame):
            df = catalog

    def start_guider(self, start_time=None, end_time=None, exptime=30,
                     image_prefix="rc", max_move=None, min_move=None,
                     data_dir=None, debug=False, create_region_file=False,
                     wait_time=5):
        """

        :param start_time:
        :param end_time:
        :param exptime:
        :param image_prefix:
        :param max_move:
        :param min_move:
        :return:
        """
        start = time.time()
        # 1. Setup constraints
        if not max_move:
            max_move = self.max_move
        if not min_move:
            min_move = self.min_move
        first_image = None
        first_positions_df = None

        # 2. Set up time ranges to look for images, if no
        # times are given extrapolate from the current time and the exposure time
        if not start_time:
            start_time = datetime.datetime.utcnow()

        if not end_time:
            end_time = (start_time
                        + datetime.timedelta(seconds=exptime))

        # 3. Get all the images and sort them sequentially by file name
        # TODO replace this with a function to sort by obstime in header
        if not data_dir:
            data_dir = os.path.join(self.data_dir,
                                    datetime.datetime.utcnow().strftime("%Y%m%d"))

        # 4. Find or wait for the first image to get the initial points

        first_image = None
        already_processed_list = []
        log = open("%s_guide.txt" % start_time, 'w')
        self.too_big_count = 0
        read_error = 0

        if debug:
            # In debug mode we assume that all the images have already been
            # taken and don't bother with wait times
            print("In the RC Guider Debug", start_time, end_time)
            print("Looking in", os.path.join(data_dir, image_prefix + "*.fits"))

            images = sorted(glob.glob(os.path.join(data_dir, image_prefix + "*.fits")))
            #print(images)
            for img in images:
                base = os.path.basename(img)
                obstime = base.replace(image_prefix, "").split(".")[0]
                obstime_str = obstime
                obstime = datetime.datetime.strptime(obstime, "%Y%m%d_%H_%M_%S")

                if start_time < obstime < end_time:

                    if not first_image:
                        print("Checking if first image")
                        df = self._get_catalog_positions(img)
                        if df.empty:
                            continue
                        first_image = img
                        xpos = df['X_IMAGE'].values
                        ypos = df['Y_IMAGE'].values

                        data = fits.getdata(img)
                        refined_points = centroid_sources(data, xpos, ypos, box_size=30,
                                                        centroid_func=centroid_2dg)

                        x_offset = (xpos - refined_points[0]) * -.394
                        y_offset = (ypos - refined_points[1]) * -.394

                        indexes = self.detect_outlier(x_offset, y_offset, return_index=True)

                        if len(indexes) >= 1:
                            print(indexes, 'more than 1')
                            for index in sorted(indexes, reverse=True):
                                new_x = np.delete(refined_points[0], index)
                                new_y = np.delete(refined_points[1], index)

                            orgin_points = [new_x, new_y]
                        else:
                            orgin_points = refined_points

                        #Check to make sure valid points
                        bkg = np.mean(data)

                        for j in range(orgin_points[0].size):
                            print(orgin_points[0][j], orgin_points[1][j])
                            x_1 = int(orgin_points[0][j] - 10)
                            x_2 = int(orgin_points[0][j] + 10)
                            y_1 = int(orgin_points[1][j] - 10)
                            y_2 = int(orgin_points[1][j] + 10)

                            bkg_star = np.mean(data[y_1:y_2, x_1:x_2])

                            print(bkg, bkg_star, 'star')
                            if bkg_star < bkg:
                                print(orgin_points[0][j], orgin_points[1][j], 'bad_staR')

                        print(orgin_points, "Orgin points")
                        if create_region_file:
                            reg = open(img + '.reg', 'w')
                            for i in range(orgin_points[0].size):
                                reg.write("point(%s, %s)\n" % (orgin_points[0][i], orgin_points[1][i]))
                            reg.close()

                        continue

                    data2 = fits.getdata(img)
                    new_points = centroid_sources(data2, orgin_points[0],
                                                  orgin_points[1],
                                                  centroid_func=centroid_2dg,
                                                  box_size=30)

                    #print(orgin_points[0], orgin_points[1], "Orgin")
                    #print(new_points[0], new_points[1], "NEW")

                    if create_region_file:
                      reg = open(img + '.reg', 'w')
                      for i in range(new_points[0].size):
                          reg.write("point(%s, %s)\n" % (new_points[0][i], new_points[1][i]))
                      reg.close()

                    x_offset = (new_points[0] - orgin_points[0]) * -.394
                    y_offset = (new_points[1] - orgin_points[1]) * -.394

                    ret = self.detect_outlier(x_offset, y_offset)

                    #x_offset = self._reject_outliers((new_points[0] - orgin_points[0]) * -.394)
                    #y_offset = self._reject_outliers((new_points[1] - orgin_points[1]) * -.394)

                    x_offset = round(np.mean(x_offset), 3)
                    y_offset = round(np.mean(y_offset), 3)
                    print(obstime_str, x_offset, y_offset)

                    if .05 < abs(x_offset) < 2.0 and .05 < abs(y_offset) < 2.0:
                        cmd = "PT %s %s" % (x_offset, y_offset)

                    elif abs(x_offset) > .05 and abs(y_offset) < .05:
                        cmd = "PT %s 0" % x_offset

                    elif abs(x_offset) < .05 and abs(y_offset) > .05:
                        cmd = "PT 0 %s" % y_offset

                    elif abs(x_offset) > 2.0 and abs(y_offset) > 2.0:
                        print("Offsets too bigx")
                        self.too_big_count += 1
                        if self.too_big_count >= 2 and abs(x_offset) < 5.5 and abs(y_offset) < 5.5:
                            cmd = "PT %s %s" % (x_offset, y_offset)

                        elif self.too_big_count >=2:
                            print("Recentering")
                            first_image = ""
                            self.too_big_count = 0
                    else:
                        print(x_offset, y_offset)
                    log.write("%s,%s,%s\n" % (obstime_str, x_offset, y_offset))
                else:
                    continue

        #log.close()    # self.socket.send("GM %s %s 10 10 \n" % (x_offset, y_offset))

        while datetime.datetime.utcnow() < end_time:
            print("In the RC Guider Loop", start_time, end_time)
            print("Looking in", os.path.join(data_dir, image_prefix + "*.fits"))
            time.sleep(5)
            images = sorted(glob.glob(os.path.join(data_dir, image_prefix + "*.fits")))
            for img in images:
                if img in already_processed_list:
                    continue
                base = os.path.basename(img)
                obstime = base.replace(image_prefix, "").split(".")[0]
                obstime_str = obstime
                obstime = datetime.datetime.strptime(obstime, "%Y%m%d_%H_%M_%S")

                if start_time < obstime < end_time:

                    if not first_image:
                        print("Checking if first image")
                        df = self._get_catalog_positions(img)
                        if df.empty:
                            already_processed_list.append(img)
                            continue
                        first_image = img
                        xpos = df['X_IMAGE'].values
                        ypos = df['Y_IMAGE'].values

                        data = fits.getdata(img)
                        refined_points = centroid_sources(data, xpos, ypos, box_size=30,
                                                        centroid_func=centroid_2dg)

                        x_offset = (xpos - refined_points[0]) * -.394
                        y_offset = (ypos - refined_points[1]) * -.394

                        indexes = self.detect_outlier(x_offset, y_offset, return_index=True)

                        if len(indexes) >= 1:
                            print(indexes, 'more than 1')
                            for index in sorted(indexes, reverse=True):
                                new_x = np.delete(refined_points[0], index)
                                new_y = np.delete(refined_points[1], index)

                            orgin_points = [new_x, new_y]
                        else:
                            orgin_points = refined_points

                        #Check to make sure valid points
                        bkg = np.mean(data)

                        for j in range(orgin_points[0].size):
                            print(orgin_points[0][j], orgin_points[1][j])
                            x_1 = int(orgin_points[0][j] - 10)
                            x_2 = int(orgin_points[0][j] + 10)
                            y_1 = int(orgin_points[1][j] - 10)
                            y_2 = int(orgin_points[1][j] + 10)

                            bkg_star = np.mean(data[y_1:y_2, x_1:x_2])

                            print(bkg, bkg_star, 'star')
                            if bkg_star < bkg:
                                print(orgin_points[0][j], orgin_points[1][j], 'bad_staR')

                        print(orgin_points, "Orgin points")
                        if create_region_file:
                            reg = open(img + '.reg', 'w')
                            for i in range(orgin_points[0].size):
                                reg.write("point(%s, %s)\n" % (orgin_points[0][i], orgin_points[1][i]))
                            reg.close()
                        already_processed_list.append(img)
                        continue
                    try:
                        data2 = fits.getdata(img)
                    except Exception as e:
                        print(str(e))
                        already_processed_list.append(img)
                        continue
                    new_points = centroid_sources(data2, orgin_points[0],
                                                  orgin_points[1],
                                                  centroid_func=centroid_2dg,
                                                  box_size=30)

                    #print(orgin_points[0], orgin_points[1], "Orgin")
                    #print(new_points[0], new_points[1], "NEW")

                    if create_region_file:
                      reg = open(img + '.reg', 'w')
                      for i in range(new_points[0].size):
                          reg.write("point(%s, %s)\n" % (new_points[0][i], new_points[1][i]))
                      reg.close()

                    x_offset = (new_points[0] - orgin_points[0]) * -.394
                    y_offset = (new_points[1] - orgin_points[1]) * -.394

                    ret = self.detect_outlier(x_offset, y_offset)

                    #x_offset = self._reject_outliers((new_points[0] - orgin_points[0]) * -.394)
                    #y_offset = self._reject_outliers((new_points[1] - orgin_points[1]) * -.394)

                    x_offset = round(np.mean(x_offset), 3)
                    y_offset = round(np.mean(y_offset), 3)
                    print(obstime_str, x_offset, y_offset)   
                    already_processed_list.append(img)

                    if .05 < abs(x_offset) < 2.0 and .05 < abs(y_offset) < 2.0:
                        cmd = "PT %s %s" % (x_offset, y_offset)
                        print(self.ocs.tel_offset(x_offset, y_offset))
                    elif abs(x_offset) > .05 and abs(y_offset) < .05:
                        cmd = "PT %s 0" % x_offset
                        print(self.ocs.tel_offset(x_offset, 0))
                    elif abs(x_offset) < .05 and abs(y_offset) > .05:
                        cmd = "PT 0 %s" % y_offset
                        print(self.ocs.tel_offset(0, y_offset))
                    elif abs(x_offset) > 2.0 and abs(y_offset) > 2.0:
                        print("Offsets too bigx")
                        self.too_big_count += 1
                        if self.too_big_count >= 2 and abs(x_offset) < 5.5 and abs(y_offset) < 5.5:
                            cmd = "PT %s %s" % (x_offset, y_offset)
                            print(self.ocs.tel_offset(x_offset, y_offset))
                        elif self.too_big_count >=2:
                            print("Recentering")
                            cmd = "PT %s %s No offset" % (x_offset, y_offset)
                            self.too_big_count = 0
                            first_image = ""

                    else:
                        cmd = ""
                        print("NO OFFSET NEEDED FOR IMAGES:", img)
                        #self.socket.send(b"PT %s 0 \r" % (x_offset))
                        #data = self.socket.recv(2048)
                        #print(data)
                    print(cmd, "cmd")
                    log.write("%s,%s,%s\n" % (obstime_str, round(np.median(x_offset), 3), round(np.median(y_offset), 3)))
                else:
                    already_processed_list.append(img)
                    continue
        print("Closing log file")
        log.close()


if __name__ == "__main__":
    x = Guide(do_connect=False)
    start = datetime.datetime.strptime("20191211_10_55_14", "%Y%m%d_%H_%M_%S")
    end = datetime.datetime.strptime("20191211_11_28_36", "%Y%m%d_%H_%M_%S")
    x.start_guider(start, end, debug=True, create_region_file=True, data_dir='/data2/sedm/20191211/')
