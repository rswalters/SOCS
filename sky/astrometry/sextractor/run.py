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

# TODO Add logging


class Sextractor:
    def __init__(self):
        """
        Class wrapper to access the sextractor program

        """
        self.sex_exec = params["sextractor"]["exec_path"]
        self.default_config = params["sextractor"]["config_file"]
        self.default_cat_path = params["sextractor"]["default_path"]
        self.run_sex_cmd = "%s -c %s " % (self.sex_exec, self.default_config)

        self.radius=10
        self.y_max = 2000
        self.y_min = 50

    def _create_region_file(self, catalog, df=False, radius=-1):
        """
        Create a region file from a sextractor catalog by using the pandas
        dataframe

        :param catalog: Sextractor catalog file path
        :param df: pandas data frame
        :param radius: Circle size in pixels
        :return: Region file path

        """
        reg_file = catalog + '.reg'

        if radius == -1:
            radius = self.radius

        if isinstance(df, bool):
            cat_data = ascii.read(catalog)
            df = cat_data.to_pandas()

        data = open(reg_file, 'w')

        for ind in df.index:
            data.write("circle(%s, %s, %s\n" % (df["X_IMAGE"][ind],
                                                df["Y_IMAGE"][ind],
                                                radius))
        data.close()

        return reg_file

    def _reject_outliers(self, data, m=.5):
        """
        Reject values in a numpy array
        :param data: numpy array or list
        :param m: max deviation in arcseconds
        :return: filtered numpy array
        """
        return data[abs(data - np.mean(data)) < m * np.std(data)]

    def run(self, input_image, output_file=None, save_in_separate_dir=True,
            create_region_file=True, overwrite=False):

        """
        Run sextractor on a fits file.  The default parameters for sextractor
        can be found in default.sex file.  The output is the sextractor
        catalog

        :param input_image: Fits image path
        :param output_file: Output file path
        :param save_in_separate_dir: If true then save the output catalog to
                                     a subdirectory where the raw file resides
        :param create_region_file: Create a ds9 region file that contains the
                                   extracted stars
        :param overwrite: Return the existing sextractor file if it already
                          exists.

        :return: dictionary with elapsed time to run the command and path of
                 the sextractor catalog
        """
        start = time.time()

        # 1. Start by making sure the input file exists
        if not os.path.exists(input_image):
            return {"elaptime": time.time()-start,
                    "error": "%s does not exists"}

        # 2. If no output file is given then we append to the original file
        # name
        if not output_file:
            if save_in_separate_dir:
                base_path = os.path.dirname(input_image)
                base_name = os.path.basename(input_image)
                save_path = os.path.join(base_path, "sextractor_catalogs")
                if not os.path.exists(save_path):
                    os.mkdir(save_path)
                output_file = os.path.join(save_path, base_name+'.cat')
            else:
                output_file = input_image + '.cat'

        if not overwrite:
            # If we are not overwriting the file and one already exists then
            # we return that version
            if os.path.exists(output_file):
                return {"elaptime": time.time()-start,
                        "data": output_file}

        # 3. If we made it here then it's time to run the command.

        # Lets just make sure there are no old files in place
        if os.path.exists(self.default_cat_path):
            os.remove(self.default_cat_path)

        # Run the sextractor command
        subprocess.call("%s %s" % (self.run_sex_cmd, input_image),
                        stdout=subprocess.DEVNULL, shell=True)

        # 4. If everything ran successfully we should have a new file called image.cat
        if not os.path.exists(self.default_cat_path):
            return {'elaptime': time.time()-start,
                    'error': "Unable to run the sextractor command"}

        # 5. Move the file to it's output directory
        shutil.move(self.default_cat_path, output_file)

        # 6. Create a region file using a pandas dataframe
        if create_region_file:
            self._create_region_file(output_file)

        return {"elaptime": time.time()-start,
                "data": output_file}

    def filter_catalog(self, catalog, mag_quantile=.8, ellip_quantile=.25,
                       create_region_file=True):
        """
        Filter a sextractor catalog to using only stars that aren't saturated
        :param catalog: file path of the sextractor catalog file
        :param mag_quantile: float, Magnitude rejection value 0-1
        :param ellip_quantile: flot, Ellipse rejection value 0-1
        :param create_region_file:
        :return: dictionary with elapsed time and dataframe of filtered data
                 from sextractor catalog
        """

        start = time.time()
        # Check to see if the file exists
        if not os.path.exists(catalog):
            return {"elaptime": time.time()-start,
                    "error": "%s does not exist" % catalog}

        # Use the ascii.read command to put the data in a format so that if can
        # be transformed into a pandas dataframe
        data = ascii.read(catalog)
        df = data.to_pandas()

        # Filter the data
        mag = df['MAG_BEST'].quantile(mag_quantile)
        ellip = df['ELLIPTICITY'].quantile(ellip_quantile)
        df = df[(df['MAG_BEST'] < mag) & (df['ELLIPTICITY'] < ellip)]
        df = df[(df['Y_IMAGE'] < self.y_max) & (df['Y_IMAGE'] > self.y_min)]

        # Write a new region file if requested
        if create_region_file:
            self._create_region_file(catalog, df)

        # Return the filtered dataframe
        return {"elaptime": time.time()-start, "data": df}

    def get_fwhm(self, catalog, do_filter=True, ellip_constraint=.2,
                 create_region_file=True):
        """
        Get the average fwhm of sextractor catalog

        :param catalog: Sextractor catalog file path
        :param do_filter: Filter the data by RC position and ellipse size
        :param ellip_constraint: float, 0-1 Values closer to 0 are more round
        :param create_region_file: Create a ds9 region file of new filtered
                                   stars
        :return: average fwhm of stars in the sextractor catalog
        """

        # Read in the sextractor catalog and convert to dataframe
        if catalog[-4:] == 'fits':
            ret = self.run(catalog)
            if 'data' in ret:
                catalog = ret['data']

        data = ascii.read(catalog)
        df = data.to_pandas()

        # Assume a numerical value for the average fwhm in case nothing passes our
        # filters
        avgfwhm = 0

        # Filter the data
        if do_filter:

            # Image cut to avoid the cross hairs in the RC images
            df = df[(df['X_IMAGE'] > 250) & (df['X_IMAGE']) < 4000]
            df = df[(df['Y_IMAGE'] > 250) & (df['Y_IMAGE']) < 3400]

            # Filter any stars that had a processing flag and only return those
            # stars that are below our ellipse constraint
            df = df[(df['FLAGS'] == 0) & (df['ELLIPTICITY'] < ellip_constraint)]

            # Reject any the FWHM of any outliers
            d = self._reject_outliers(df['FWHM_IMAGE'].values)

            # TODO determine where the .49 value came from?  It should be the
            #      pixel scale which is .394"
            avgfwhm = np.median(d) * .49

            df = df.sort_values(by=['MAG_BEST'])
            df = df[0:5]

            if create_region_file:
                self._create_region_file(catalog, df)

        print(df['FWHM_IMAGE'].values)
        fwhm = np.median(df['FWHM_IMAGE'].values) * .49
        print(fwhm)

        return avgfwhm

    def run_loop(self, obs_list, header_field='FOCPOS', overwrite=False,
                 catalog_field='FWHM_IMAGE', filter_catalog=True):
        """
        Given a list of fits image find the best position from the header field
        and return the value

        :param obs_list: List of image file paths
        :param overwrite: overwrite existing sextractor files
        :param header_field: header field in fits file to use to find the best
                             value
        :param catalog_field: field in the sextractor catalog to use to find
                              best value
        :param filter_catalog: bool, determine if we should filter the data in
                               the sextractor catalog
        :return: dictionary with elapsed time and subdict of best position and
                 poly coefficients
        """
        start = time.time()
        header_field_list = []
        catalog_field_list = []
        error_list = []

        # 1. Start by looping through the image list
        for obs in obs_list:

            # 2. Before preforming any analysis do a sainty check to make
            # sure the file exists
            if not os.path.exists(obs):
                header_field_list.append(np.NaN)
                catalog_field_list.append(np.NaN)
                error_list.append(np.NaN)
                continue

            # 3. Now open the file and get the header information
            try:
                header_field_list.append(float(fits.getheader(obs)[header_field]))
            except Exception as e:
                header_field_list.append(np.NaN)
                catalog_field_list.append(np.NaN)
                error_list.append(np.NaN)
                continue

            # 4. We should now be ready to run sextractor
            ret = self.run(obs, overwrite=overwrite)

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

    csvoutput = open('test.csv', 'w')
    csvoutput.write("image, fwhm\n")
    for i in data_list:
        ret = x.get_fwhm(i)
        csvoutput.write("%s,%s\n" % (i, ret))
    csvoutput.close()
    #print(data_list[0])
    #print(x.get_catalog_positions(data_list[2]))
    #print(x.run(data_list[0], overwrite=True))
    #ret = x.run_loop(data_list, overwrite=False)
    #print(ret)
