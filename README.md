Solar disk reconstruction from SHG (spectroheliography) SER files. Only 16bit files are accepted. No AVI files are accepted.
If no spectral line can recognised in the SER file, the program will stop.

Install the most recent version of Python from python.org. During Windows installation, check the box to update the PATH.

For Windows, double click the windows_setup file to install the needed Python libraries.

Usage: launch SHG_MAIN (by double clicking under Windows). A Windows Desktop shortcut can also be created.

In the Python GUI window, enter the name of the SER file(s) to be processed. Batch processing is possible but will halt if a file is unsuitable.

Check the "Show graphics" box for a live reconstruction display, a graphic of the geometry correction and a quick view of the final images. 
This will increase processing time significantly. This feature is not recommended for batch processing.

If the "Save FITS files" box is checked, the following files will be stored in the same directory as the SER file (with the option of .fits or .fit file extension):

- xx_mean.fits: average image of all the frames in the SER video of the spectral line
- xx_img.fits: raw image reconstruction
- xx_corr.fits: image corrected for outliers
- xx_circle.fits: circularized image
- xx_flat.fits: corrected flat image
- xx_recon.fits: final image, corrected for tilt
- xx_clahe.fits: final image, with Contrast Limited Adaptive Histogram Equalization

If the "Save CLAHE.png image only" box is checked, then only the final PNG image with Contrast Limited Adaptive Histogram Equalization will be saved.

Y/X ratio: enter a specific Y/X ratio, if this is known. Leave blank for auto-correction. Enter 1 if no correction desired.

Tilt angle: enter a specific tilt angle in degrees. Leave blank for auto-correction. Enter 0 if no tilt correction desired.

Pixel offset: offset in pixels from the minimum of the line to reconstruct the image on another wavelength (displaced from the central minimum).

Geometry correction may fail under certain circumstances and the program will stop. In this case, enter the Y/X ratio and Tilt angle manually (try 1, 0 initially).

For rapid processing during data acquisition, make sure "Show graphics" is off. Automatic geometry correction also takes additional time.
Moroever, if Y/X is set to 1, distortion due to inappropriate scanning speed vs frame rate can be recognised and optimised.
Similarly, if Tilt is set to 0, instrument misalignment can be recognised and corrected.
