import os
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from astropy import units as u
import subprocess
import time


def solve_astrometry(img, radius=2.5, with_pix=True, downsample=False,
                     tweak=3, make_plots=False, repeat=True,
                     downsample_size=2):
    """
    Use astrometry.net local database to solve the astrometry of the input
    image


    :param img: str, file path of raw fits image
    :param make_plots: bool, determine if to make additional output files
                       from astrometry.net solve-field
    :param radius: float, default radius size for solve-field
    :param with_pix: bool, if true set the scale unit size to arcseconds
    :param repeat: bool, if true then this command indicates that we already
                         attempted one solve. Currently it is used when
                         running the downsample command
    :param tweak: int, astrometry.net input
    :param downsample: bool, determine if to add the the downsample option
    :param downsample_size: int, amount to downsize the image for solve-field
    :return: dict, returns the elapsed time and file path of the new solved
                   image

    """
    start = time.time()

    # 1. Get the needed header information for the solve field command
    image_header = fits.getheader(img)

    # If the object ra and dec keywords are missing check for just the RA and
    # DEC keywords
    try:
        ra, dec = image_header['OBJRA'], image_header['OBJDEC']
    except Exception as e:
        ra, dec = image_header['RA'], image_header['DEC']

    # 2. Create the solved astronomy base name
    astro = os.path.join(os.path.dirname(img), "a_" + os.path.basename(img))

    print("Solving astrometry on field with (ra,dec)=",
          ra, dec, "Image", img, "New image", astro)

    # Check if we are downsampling the image which has had some success in
    # solving the astrometry of some failed images.
    if downsample:
        downsample_str = '--downsample %s' % downsample_size
    else:
        downsample_str = ''

    # 3. Create the base solve-field command
    if make_plots:
        cmd = (" solve-field --ra %s --dec %s --radius "
               "%.4f -t %d --overwrite %s "
               "" % (ra, dec, radius, tweak, img))
    else:
        cmd = (" solve-field --ra %s --dec %s --radius "
               "%.4f -p --new-fits %s -W none -B none -M none "
               "--scale-low 0.355 --scale-high 0.400 --nsigma 12 "
               "-R none -S none -t %d --overwrite %s --parity neg %s"
               "" % (ra, dec, radius, astro, tweak, img, downsample_str))

    if with_pix:
        cmd = cmd + " --scale-units arcsecperpix --"

    # Output error to tmp file
    cmd = cmd + " > /tmp/astrometry_fail  2>/tmp/astrometry_fail"

    # Run the solve-field command in a subprocess.  The timeout is set
    # to avoid getting stuck
    try:
        subprocess.call(cmd, shell=True, timeout=120)
    except Exception as e:
        return {'elaptime': time.time() - start,
                'error': 'Failed to launch solve-field: %s' % str(e)}

    # Cleaning up the extras after astrometry.net
    if os.path.isfile(img.replace(".fits", ".axy")):
        os.remove(img.replace(".fits", ".axy"))
    if os.path.isfile(img.replace(".fits", "-indx.xyls")):
        os.remove(img.replace(".fits", "-indx.xyls"))

    if not os.path.isfile(astro):
        # If there is not an output file then the astrometry failed. We can
        # try again but by downsampling the data.  To keep from doing this
        # over and over we just use repeat variable to skip
        if repeat:
            solve_astrometry(img, radius=radius, with_pix=with_pix,
                             tweak=tweak, repeat=False,
                             make_plots=make_plots, downsample=True)
        return {'elaptime': time.time()-start, 'error': 'Failed to solve'}

    return {'elaptime': time.time()-start, 'data': astro}


def get_offset_to_reference(image, get_ref_pixel_from_header=False,
                            reference_pixels=(1293, 1280), header_ra='OBJRA',
                            header_dec='OBJDEC'):
    """
    Given an image with solved WCS. Compute the offset to the
    reference pixel
    :param image: astrometry solved image path
    :param header_ra: keyword for fits header object ra
    :param header_dec: keyword for fits header object dec
    :param get_ref_pixel_from_header: bool, if true get the reference
                                      pixel from the header
    :param reference_pixels: tuple of x,y reference position
    :return: dict, dictionary of elapsed time and sub-dict of
                   ra, dec offsets in arcseconds
    """
    start = time.time()
    # 1. Start by checking if the image exists
    if not os.path.exists(image):
        return {'elaptime': time.time()-start,
                'error': 'Solved astrometry file does not exists'}


    # 2. Get the object coordinates from header and convert to degrees when
    # needed.
    image_header = fits.getheader(image)
    obj_ra, obj_dec = image_header[header_ra], image_header[header_dec]

    if not isinstance(obj_ra, float) and not isinstance(obj_dec, float):
        objCoords = SkyCoord(obj_ra, obj_dec, unit=(u.hour, u.deg), frame='icrs')
    else:
        objCoords = SkyCoord(obj_ra, obj_dec, unit=(u.deg, u.deg), frame='icrs')

    # 3. Get the WCS reference pixel position
    wcs = WCS(fits.getheader(image))

    if get_ref_pixel_from_header:
        x, y = image_header['crpix1'], image_header['crpix2']
    else:
        x, y = reference_pixels

    ref_ra, ref_dec = wcs.all_pix2world(x, y, 0)

    # 4. Get the ra and dec separation between the object and reference pixel
    refCoords = SkyCoord(ref_ra, ref_dec, unit='deg', frame='icrs')

    dra, ddec = objCoords.spherical_offsets_to(refCoords)

    return {'elaptime': time.time()-start, 'data': {'code': 0,
                                                    'ra_offset': round(-1*dra.arcsec, 3),
                                                    'dec_offset': round(-1*ddec.arcsec, 3)}}


def calculate_offset(raw_image, overwrite=True,
                     parse_directory_from_file=True,
                     base_dir="/home/rsw/", make_plots=False):
    """
    Given a raw fits image, calculate the offset needed to move the input
    object to the reference pixel

    :param raw_image: String of the raw image path location
    :param parse_directory_from_file: Use the file to parse the utdate
                                      directory that most standard image
                                      files are saved in.
    :param base_dir: The base directory
    :param make_plots: Decide whether to keep and make plots from the
                       astrometry and sextractor commands

    :param overwrite: bool, if true then we recalculate the offsets otherwise
                      if the existing astrometry file exist use that
    :return: dict, Dictionary of time to complete the command and another
                   dictionary of the calculated offsets.  
    """
    start = time.time()

    if parse_directory_from_file:
        raw_image = raw_image.split('/')[-2:]
        raw_image = os.path.join(base_dir, raw_image[0], raw_image[1])

    # 1. Check if the solved output file exist for the raw file, we
    # expect the files to be in the same directory.
    astro = os.path.join(os.path.dirname(raw_image),
                         "a_" + os.path.basename(raw_image))

    if overwrite:
        ret = solve_astrometry(raw_image, make_plots=make_plots)
        if 'data' in ret:
            astro = ret['data']

    # 2. Now check if the solved file exist and solve the offset
    if os.path.exists(astro):
        return get_offset_to_reference(astro)
    else:
        return {'elaptime': time.time()-start, 'error': 'Unable to solve astrometry'}


if __name__ == "__main__":
    print(calculate_offset('/home/rsw/rc20190912_09_20_50.fits', parse_directory_from_file=False))