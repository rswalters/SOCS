import os
import glob
import time
from astropy.io import ascii, fits
import numpy as np
import subprocess
import shutil
import yaml

SR = os.path.abspath(os.path.dirname(__file__) + '/../../../')
with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
    params = yaml.load(data_file, Loader=yaml.FullLoader)


class Sextractor:
    def __init__(self):
        """

        :param config:
        """
        self.sex_exec = params["sextractor"]["exec_path"]
        self.default_config = params["sextractor"]["config_file"]
        self.default_cat_path = params["sextractor"]["default_path"]
        self.run_sex_cmd = "%s -c %s " % (self.sex_exec, self.default_config)

        self.y_max = 2000
        self.y_min = 50

    def _output_type(self, catalog, output_type='ascii'):
        """

        :param catalog:
        :param output_type:
        :return:
        """
        pass

    def run(self, input_image, output_file=None, save_in_seperate_dir=True,
            output_type=None, create_region_file=True, overwrite=False):

        """

        :param input_image:
        :param output_file:
        :param output_type:
        :return:
        """
        start = time.time()

        # 1. Start by making sure the input file exists
        if not os.path.exists(input_image):
            return {"elaptime": time.time()-start,
                    "error": "%s does not exists"}

        # 2. If no output file is given then we append to the original file
        # name
        if not output_file:
            if save_in_seperate_dir:
                base_path = os.path.dirname(input_image)
                base_name = os.path.basename(input_image)
                save_path = os.path.join(base_path, "sextractor_catalogs")
                if not os.path.exists(save_path):
                    os.mkdir(save_path)
                output_file = os.path.join(save_path, base_name+'.cat')
            else:
                output_file = input_image + '.cat'

        if not overwrite:
            if os.path.exists(output_file):
                if not output_type:
                    return {"elaptime": time.time()-start,
                            "data": output_file}
                else:
                    return {"elaptime": time.time()-start,
                            "data": self._output_type(output_file,
                                                      output_type=output_type)}

        # 3. If we made it here then it's time to run the command.

        # Lets just make sure there are no old files in place
        if os.path.exists(self.default_cat_path):
            os.remove(self.default_cat_path)
        print("HERE1")
        # Run the sextractor command
        subprocess.call("%s %s" % (self.run_sex_cmd, input_image),
                        stdout=subprocess.DEVNULL, shell=True)

        # 4. If everything ran successfully we should have a new file called image.cat
        if not os.path.exists(self.default_cat_path):
            return {'elaptime': time.time()-start,
                    'error': "Unable to run the sextractor command"}
        print("HERE")
        shutil.move(self.default_cat_path, output_file)

        if create_region_file:
            reg_file = output_file + '.reg'
            cat_data = ascii.read(output_file)
            df = cat_data.to_pandas()
            data = open(reg_file, 'w')
            for ind in df.index:
                data.write("circle(%s, %s, %s\n" % (df["X_IMAGE"][ind],
                                                    df["Y_IMAGE"][ind],
                                                    10))
            data.close()
            print(reg_file)
        return {"elaptime": time.time()-start,
                "data": output_file}

    def catalog_to_reigon(self, catalog):
        """

        :param catalog:
        :return:
        """

        pass

    def filter_catalog(self, catalog, mag_quantile=.8, ellp_quantile=.25,
                       create_region_file=True, radius=10):

        start = time.time()

        if not os.path.exists(catalog):
            return {"elaptime": time.time()-start,
                    "error": "%s does not exist" % catalog}
        data = ascii.read(catalog)

        df = data.to_pandas()
        mag = df['MAG_BEST'].quantile(mag_quantile)
        ellip = df['ELLIPTICITY'].quantile(ellp_quantile)
        df = df[(df['MAG_BEST'] < mag) & (df['ELLIPTICITY'] < ellip)]
        df = df[(df['Y_IMAGE'] < self.y_max) & (df['Y_IMAGE'] > self.y_min)]

        if create_region_file:
            reg_file = catalog + '.reg'
            data = open(reg_file, 'w')
            for ind in df.index:
                data.write("circle(%s, %s, %s\n" % (df["X_IMAGE"][ind],
                                                    df["Y_IMAGE"][ind],
                                                    radius))
            data.close()
            print(reg_file)

        return {"elaptime": time.time()-start, "data": df}

    def _reject_outliers(self, data, m=.5):
        return data[abs(data - np.mean(data)) < m * np.std(data)]

    def get_fwhm(self, catalog, do_filter=True,
                              ellip_constraint=.2,
                              create_region_file=True):

        # Read in the sextractor catalog and convert to dataframe
        if catalog[-4:] == 'fits':
            ret = self.run(catalog)
            #print(ret)
            if 'data' in ret:
                catalog = ret['data']
        print(catalog)
        data = ascii.read(catalog)

        df = data.to_pandas()
        avgfwhm = 0
        print("HERER")
        if do_filter:
            df = df[(df['X_IMAGE'] > 250) & (df['X_IMAGE']) < 4000]
            df = df[(df['Y_IMAGE'] > 250) & (df['Y_IMAGE']) < 3400]
            df = df[(df['FLAGS'] == 0) & (df['ELLIPTICITY'] < ellip_constraint)]

            d = self._reject_outliers(df['FWHM_IMAGE'].values)
            avgfwhm = np.median(d) * .49

            print(avgfwhm)

            df = df.sort_values(by=['MAG_BEST'])
            df = df[0:5]



            if create_region_file:
                reg_file = catalog + '.reg'
                data = open(reg_file, 'w')
                for ind in df.index:
                    data.write("circle(%s, %s, %s\n" % (df["X_IMAGE"][ind],
                                                        df["Y_IMAGE"][ind],
                                                        20))
                data.close()
                print(reg_file)
        print(df['FWHM_IMAGE'].values)
        fwhm = np.median(df['FWHM_IMAGE'].values) * .49
        print(fwhm)

        return avgfwhm

    def run_loop(self, obs_list, header_field='FOCPOS', overwrite=False,
                 catalog_field='FWHM_IMAGE', filter_catalog=True,
                 save_catalogs=True, ):
        """

        :param obs_list:
        :param header_field:
        :param catalog_field:
        :param filter_catalog:
        :return:
        """
        start = time.time()
        header_field_list = []
        catalog_field_list = []
        error_list = []

        # 1. Start by looping through the image list
        for i in obs_list:
            # 2. Before preforming any analysis do a sainty check to make
            # sure the file exists
            if not os.path.exists(i):
                header_field_list.append(np.NaN)
                catalog_field_list.append(np.NaN)
                error_list.append(np.NaN)
                continue

            # 3. Now open the file and get the header information
            try:
                header_field_list.append(float(fits.getheader(i)[header_field]))
            except:
                header_field_list.append(np.NaN)
                catalog_field_list.append(np.NaN)
                error_list.append(np.NaN)
                continue

            # 4. We should now be ready to run sextractor
            ret = self.run(i, overwrite=overwrite)

            # 5. Check that there were no errors
            if 'error' in ret:
                header_field_list.append(np.NaN)
                catalog_field_list.append(np.NaN)
                error_list.append(np.NaN)
                continue

            # 6. Filter the data if requested
            if filter_catalog:
                ret = self.filter_catalog(ret['data'])

            # 7. Again check there were no errors
            if 'error' in ret:
                header_field_list.append(np.NaN)
                catalog_field_list.append(np.NaN)
                error_list.append(np.NaN)
                continue

            # 8. Now we get the mean values for the catalog
            df = ret['data']
            if df.empty:
                header_field_list.append(np.NaN)
                catalog_field_list.append(np.NaN)
                error_list.append(np.NaN)
                continue

            # 9. Finally get the stats for the image
            catalog_field_list.append(df[catalog_field].mean())
            error_list.append(df.loc[:, catalog_field].std())
            
        catalog = np.array(catalog_field_list)
        header = np.array(header_field_list)
        std_catalog = np.array(error_list)
    
        n = len(catalog)
        print(n, catalog, 'test')
        best_seeing_id = np.nanargmin(catalog)
        # We will take 4 datapoints on the left and right of the best value.
        selected_ids = np.arange(-4, 5, 1)
        selected_ids = selected_ids + best_seeing_id
        selected_ids = np.minimum(selected_ids, n - 1)
        selected_ids = np.maximum(selected_ids, 0)
        print("FWHMS: %s, focpos: %s, Best seeing id: %d. "
              "Selected ids %s" % (catalog, header, best_seeing_id,
                                   selected_ids))

        selected_ids = np.array(list(set(selected_ids)))
    
        header = header[selected_ids]
        catalog = catalog[selected_ids]
        std_catalog = std_catalog[selected_ids]
    
        std_catalog = np.maximum(1e-5, np.array(std_catalog))
    
        coefs = np.polyfit(header, catalog, w=1 / std_catalog, deg=2)
    
        x = np.linspace(np.min(header), np.max(header), 10)
        p = np.poly1d(coefs)

        print("Best focus:%.2f" % x[np.argmin(p(x))], coefs[0])

        return {'elaptime': time.time()-start,
                'data': [x[np.argmin(p(x))], coefs[0]]}


if __name__ == "__main__":
    x = Sextractor()
    data_list = sorted(glob.glob("/scr2/bigscr_rsw/guider_images/*.fits"))

    data = open('test.csv', 'w')
    data.write("image, fwhm\n")
    for i in data_list:
        ret = x.get_fwhm(i)
        data.write("%s,%s\n" % (i, ret))
    data.close()
    #print(data_list[0])
    #print(x.get_catalog_positions(data_list[2]))
    #print(x.run(data_list[0], overwrite=True))
    #ret = x.run_loop(data_list, overwrite=False)
    #print(ret)
