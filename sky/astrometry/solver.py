import os
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from astropy import units as u
import subprocess
import time


def solve_astrometry(img, radius=2.5, with_pix=True, downsample="",
                     first_call=False, tweak=3, make_plots=False, repeat=True):
    """

    :param downsample:
    :param make_plots:
    :param repeat:
    :param img:
    :param radius:
    :param with_pix:
    :param first_call:
    :param tweak:
    :return:
    """
    start = time.time()
    # 1. Get the needed header information for the solve field command
    image_header = fits.getheader(img)
    try:
        ra, dec = image_header['OBJRA'], image_header['OBJDEC']
    except Exception as e:
        ra, dec = image_header['RA'], image_header['DEC']

    # 2. Create the solved astronomy base name
    astro = os.path.join(os.path.dirname(img), "a_" + os.path.basename(img))

    print("Solving astrometry on field with (ra,dec)=",
          ra, dec, "Image", img, "New image", astro)

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
               "" % (ra, dec, radius, astro, tweak, img, downsample))

    if with_pix:
        cmd = cmd + " --scale-units arcsecperpix --"

    print(cmd)

    cmd = cmd + " > /tmp/astrometry_fail  2>/tmp/astrometry_fail"
    try:
        subprocess.call(cmd, shell=True, timeout=120)
    except Exception as e:
        return {'elaptime': time.time() - start,
                'error': 'Failed to launch solve-field: %s' % str(e)}

    # Cleaning after astrometry.net
    if os.path.isfile(img.replace(".fits", ".axy")):
        os.remove(img.replace(".fits", ".axy"))
    if os.path.isfile(img.replace(".fits", "-indx.xyls")):
        os.remove(img.replace(".fits", "-indx.xyls"))
    if os.path.isfile("none"):
        os.remove("none")

    if not os.path.isfile(astro):
        if repeat:
            solve_astrometry(img, radius=radius, with_pix=with_pix,
                         first_call=first_call, tweak=tweak, repeat=False,
                         make_plots=make_plots, downsample="--downsample 2")
        return {'elaptime': time.time()-start, 'error': 'Failed to solve'}

    return {'elaptime': time.time()-start, 'data': astro}


def get_offset_to_reference(image, get_ref_from_header=False,
                            reference=(1293, 1280), header_ra='OBJRA',
                            header_dec='OBJDEC'):
    """
    Given an image with solved WCS. Compute the offset to the
    reference pixel
    :param header_ra:
    :param header_dec:
    :param image:
    :param get_ref_from_header:
    :param reference:
    :return:
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

    if get_ref_from_header:
        x, y = image_header['crpix1'], image_header['crpix2']
    else:
        x, y = reference

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

    :param parse_directory_from_file:
    :param base_dir:
    :param make_plots:
    :param raw_image:
    :param overwrite:
    :return:
    """
    start = time.time()

    if parse_directory_from_file:
        raw_image = raw_image.split('/')[-2:]
        raw_image = os.path.join(base_dir, raw_image[0], raw_image[1])

    # Test line
    #raw_image = '/home/rsw/rc20190912_09_20_50.fits'

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