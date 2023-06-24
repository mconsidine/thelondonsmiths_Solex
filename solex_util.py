"""
@author: Andrew Smith
contributors: Valerie Desnoux, Jean-Francois Pittet, Jean-Baptiste Butet, Pascal Berteau, Matt Considine
Version 24 June 2023

"""

import numpy as np
import matplotlib.figure
import matplotlib.pyplot as plt
from astropy.io import fits
from scipy.interpolate import interp1d
import os
#import time
from scipy.signal import savgol_filter
import cv2
import sys
import math
from scipy.ndimage import gaussian_filter1d
from numpy.polynomial.polynomial import polyval
from video_reader import *
import tkinter as tk
import ctypes # Modification Jean-Francois: for reading the monitor size
import cv2
from scipy.optimize import curve_fit

mylog = []


def clearlog():
    mylog.clear()


def logme(s):
    print(s)
    mylog.append(s + '\n')

# return values in an array not "m-far" from mean
def reject_outliers(data, m = 2):
    bins = np.linspace(0, np.max(data) + 1, 64)
    inds = np.digitize(data, bins)
    modals, counts = np.unique(inds, return_counts=True)
    modal_value = bins[np.argmax(counts)]
    median_value = np.median(data)
    #print('modal value', modal_value)
    d = np.abs(data - median_value)
    mdev = np.median(d)
    s = d/mdev if mdev else np.zeros(len(d))
    return data[s<m]


# read video and return constructed image of sun using fit
def read_video_improved(file, fit, options):
    rdr = video_reader(file)
    ih, iw = rdr.ih, rdr.iw
    FrameMax = rdr.FrameCount
    disk_list = [np.zeros((ih, FrameMax), dtype='uint16')
                 for _ in options['shift']]

    if options['flag_display']:
        screen = tk.Tk()
        sw, sh = screen.winfo_screenwidth(), screen.winfo_screenheight()
        scaling = sh/ih * 0.8
        screen.destroy()
        cv2.namedWindow('disk', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('disk', int(FrameMax * scaling), int(ih * scaling))
        cv2.moveWindow('disk', 200, 0)
        cv2.namedWindow('image', cv2.WINDOW_NORMAL)
        cv2.moveWindow('image', 0, 0)
        cv2.resizeWindow('image', int(iw * scaling), int(ih * scaling))

    col_indeces = []

    for shift in options['shift']:
        ind_l = (np.asarray(fit)[:, 0] + np.ones(ih)*shift).astype(int)

        # CLEAN if fitting goes too far
        ind_l[ind_l < 0] = 0
        ind_l[ind_l > iw - 2] = iw - 2
        ind_r = (ind_l + np.ones(ih)).astype(int)
        col_indeces.append((ind_l, ind_r))

    left_weights = np.ones(ih) - np.asarray(fit)[:, 1]
    right_weights = np.ones(ih) - left_weights

    # lance la reconstruction du disk a partir des trames
    print('reader num frames:', rdr.FrameCount)
    while rdr.has_frames():
        img = rdr.next_frame()
        for i in range(len(options['shift'])):
            ind_l, ind_r = col_indeces[i]
            left_col = img[np.arange(ih), ind_l]
            right_col = img[np.arange(ih), ind_r]
            IntensiteRaie = left_col * left_weights + right_col * right_weights
            disk_list[i][:, rdr.FrameIndex] = IntensiteRaie

        if options['flag_display'] and rdr.FrameIndex % 10 == 0:
            # disk_list[1] is always shift = 0
            cv2.imshow('image', img)
            cv2.imshow('disk', disk_list[1])
            if cv2.waitKey(
                    1) == 27:                     # exit if Escape is hit
                cv2.destroyAllWindows()
                sys.exit()
    return disk_list, ih, iw, rdr.FrameCount


def make_header(rdr):
    # initialisation d'une entete fits (etait utilisé pour sauver les trames
    # individuelles)
    hdr = fits.Header()
    hdr['SIMPLE'] = 'T'
    hdr['BITPIX'] = 32
    hdr['NAXIS'] = 2
    hdr['NAXIS1'] = rdr.iw
    hdr['NAXIS2'] = rdr.ih
    hdr['BZERO'] = 0
    hdr['BSCALE'] = 1
    hdr['BIN1'] = 1
    hdr['BIN2'] = 1
    hdr['EXPTIME'] = 0
    return hdr

# compute mean and max image of video

def detect_bord(img, axis):
    blur = cv2.blur(img, ksize=(5,5))
    ymean = np.mean(blur, axis)
    threshhold = np.median(ymean) / 5
    where_sun = ymean > threshhold
    lb = np.argmax(where_sun)
    ub = img.shape[int(not axis)] - 1 - np.argmax(np.flip(where_sun)) # int(not axis) : get the other axis 1 -> 0 and 0 -> 1
    return lb, ub

def compute_mean_max(file):
    """IN : file path"
    OUT :numpy array
    """
    rdr = video_reader(file)
    logme('Width, Height : ' + str(rdr.Width) + ' ' + str(rdr.Height))
    logme('Number of frames : ' + str(rdr.FrameCount))
    my_data = np.zeros((rdr.ih, rdr.iw), dtype='uint64')
    max_data = np.zeros((rdr.ih, rdr.iw), dtype='uint16')
    while rdr.has_frames():
        img = rdr.next_frame()
        my_data += img
        max_data = np.maximum(max_data, img)
    return (my_data / rdr.FrameCount).astype('uint16'), max_data


def compute_mean_return_fit(file, options, hdr, iw, ih, basefich0):
    """
    ----------------------------------------------------------------------------
    Use the mean image to find the location of the spectral line of maximum darkness
    Apply a 3rd order polynomial fit to the datapoints, and return the fit, as well as the
    detected extent of the line in the y-direction.
    ----------------------------------------------------------------------------
    """
    flag_display = options['flag_display']
    # first compute mean image
    # rdr is the video_reader object
    mean_img, max_img = compute_mean_max(file)
    
    if options['save_fit']:
        DiskHDU = fits.PrimaryHDU(mean_img, header=hdr)
        DiskHDU.writeto(basefich0 + '_mean.fits', overwrite='True')

    # affiche image moyenne
    if flag_display:
        screen = tk.Tk()
        sw, sh = screen.winfo_screenwidth(), screen.winfo_screenheight()
        scaling = sh/ih * 0.8
        screen.destroy()
        cv2.namedWindow('Ser mean', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Ser mean', int(iw*scaling), int(ih*scaling))
        cv2.moveWindow('Ser mean', 100, 0)
        cv2.imshow('Ser mean', mean_img)
        if cv2.waitKey(2000) == 27:                     # exit if Escape is hit
            cv2.destroyAllWindows()
            sys.exit()

        cv2.destroyAllWindows()
    y1, y2 = detect_bord(max_img, axis=1) # use maximum image to detect borders
    clip = int((y2 - y1) * 0.05)
    y1 = min(max_img.shape[0]-1, y1+clip)
    y2 = max(0, y2-clip)
    logme('Vertical limits y1, y2 : ' + str(y1) + ' ' + str(y2))
    blur_width_x = 25
    blur_width_y = int((y2 - y1) * 0.01)
    blur = cv2.blur(mean_img, ksize=(blur_width_x,blur_width_y))
    min_intensity = blur_width_x//2 + np.argmin(blur[:, blur_width_x//2:-blur_width_x//2], axis = 1) # use blurred mean image to detect spectral line
    
    p = np.flip(np.asarray(np.polyfit(np.arange(y1, y2), min_intensity[y1:y2], 3), dtype='d'))
    # remove outlier points and get new line fit
    delta = polyval(np.asarray(np.arange(y1,y2), dtype='d'), p) - min_intensity[y1:y2]
    stdv = np.std(delta)
    keep = np.abs(delta/stdv) < 3
    p = np.flip(np.asarray(np.polyfit(np.arange(y1, y2)[keep], min_intensity[y1:y2][keep], 3), dtype='d'))
    #logme('Spectral line polynomial fit: ' + str(p))

    # find shift to non-blurred minimum
    min_intensity_sharp = np.argmin(mean_img, axis = 1) # use original mean image to detect spectral line
    delta_sharp = polyval(np.asarray(np.arange(y1,y2), dtype='d'), p) - min_intensity_sharp[y1:y2]
    
    values, counts = np.unique(np.around(delta_sharp, 1),  return_counts=True)
    ind = np.argpartition(-counts, kth=2)[:2] 
    shift = values[ind[0]] # find mode
    #logme(f'shift correction : {shift}')
    
    #matplotlib.pyplot.hist(delta_sharp, np.linspace(-20, 20, 400))
    #matplotlib.pyplot.show()

    tol_line_fit = 5
    mask_good = np.abs(delta_sharp - shift) < tol_line_fit
    p = np.flip(np.asarray(np.polyfit(np.arange(y1, y2)[mask_good], min_intensity_sharp[y1:y2][mask_good], 3), dtype='d'))
    logme('Spectral line polynomial fit: ' + str(p))
    
    curve = polyval(np.asarray(np.arange(ih), dtype='d'), p)
    fit = [[math.floor(curve[y]), curve[y] - math.floor(curve[y]), y] for y in range(ih)]

    
    
    if not options['clahe_only']:
        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        ax.imshow(mean_img, cmap=matplotlib.pyplot.cm.gray)
        s = (y2-y1)//20 + 1
        ax.plot(min_intensity_sharp[y1:y2][mask_good][::s], np.arange(y1, y2)[mask_good][::s], 'rx', label='line detection')
        ax.plot(curve, np.arange(ih), label='polynomial fit')
        ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))
        ax.set_aspect(0.1)
        fig.tight_layout()
        fig.savefig(basefich0+'_spectral_line_data.png', dpi=400)
    return fit, y1, y2


'''
img: np array
borders: [minX, minY, maxX, maxY]
cirlce: (centreX, centreY, radius)
reqFlag: 0 if this was a user-requested image, else: 1 if shift = 10, 2 if shift = 0
'''
def correct_transversalium2(img, circle, borders, options, reqFlag, basefich):
    y1 = math.ceil(max(circle[1] - circle[2], borders[1]))
    y2 = math.floor(min(circle[1] + circle[2], borders[3]))
    '''
    y_s = []
    y_mean = []
    y_mean_raw = []
       
    for y in range(y1, y2):
        dx = math.floor((circle[2]**2 - (y-circle[1])**2)**0.5)
        strip = img[y, math.ceil(max(circle[0] - dx, borders[0])) : math.floor(min(circle[0] + dx, borders[2]))]

        y_s.append(y)
        y_mean.append(np.mean(reject_outliers(strip)))
        y_mean_raw.append(np.mean(strip))
        if (y == 1040 or y == 900) and 0:
            plt.plot(strip)
            plt.title('strip')
            plt.show()
        if y == 1040 and 0:
            print(y)
            plt.hist(strip, bins = range(0, 2**16, 2**10))
            plt.hist(reject_outliers(strip), bins = range(0, 2**16, 2**10))
            plt.show()
            print('mean1,2: ', np.mean(strip), np.mean(reject_outliers(strip)))
    plt.plot(y_mean)
    plt.show()
    y_mean_raw = np.array(y_mean_raw)
    '''
    y_ratios_r = [0]
    y_ratios = [0]
    for y in range(y1 + 1, y2):
        dx = math.floor((circle[2]**2 - (y-circle[1])**2)**0.5)
        strip0 = img[y - 1, math.ceil(max(circle[0] - dx, borders[0])) : math.floor(min(circle[0] + dx, borders[2]))]
        strip1 = img[y, math.ceil(max(circle[0] - dx, borders[0])) : math.floor(min(circle[0] + dx, borders[2]))]
        
        rat = np.log(strip1 / strip0)
        y_ratios.append(np.mean(rat))
        y_ratios_r.append(np.mean(reject_outliers(rat)))
        if y % 100 == 0 and 0:
            print(y)
            plt.hist(rat, bins = np.linspace(0.5, 2, 128))
            plt.savefig()
    trend = savgol_filter(y_ratios_r, min(options['trans_strength'], len(y_ratios_r) // 2 * 2 - 1), 3)

    detrended = y_ratios_r - trend
    detrended -= np.mean(detrended) # remove DC bias
    correction = np.exp(-np.cumsum(detrended))

    if 0:        
        plt.plot(y_ratios)
        plt.plot(y_ratios_r)
        plt.plot(trend)
        plt.show()
        plt.plot(correction)
        plt.show()
        
    a = 0.05 # taper width
    N = correction.shape[0]

    # Tukey taper function
    def t(x):
        if 0 <= x < a*N/2:
            return 1/2 * (1-math.cos(2*math.pi*x/(a*N)))
        elif a*N/2 <= x <= N/2:
            return 1
        elif N/2 <= x <= N:
            return t(N - x)
        print('error: weird input for taper function: ' + str(x))
        return 1

    taper = np.array([t(x) for x in range(N)])
    
    correction_t = np.ones(N) + (correction - np.ones(N)) * taper

    #plt.plot(y_s, correction)
    #plt.plot(y_s, correction_t)
    #plt.show()

    c = np.ones(img.shape[0])
    c[y1:y2] = correction_t
    #c[c<1] = 1
    options['_transversalium_cache'] = c
    if (reqFlag == 1 or (FLAG_OLD_WAY and not reqFlag)) and (not options['clahe_only']):
        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        ax.plot(c)
        ax.set_xlabel('y')
        ax.set_ylabel('transversalium correction factor')
        fig.savefig(basefich+'_transversalium_correction.png', dpi=300)
    ret = (img.T * c).T # multiply each row in image by correction factor
    ret[ret > 65535] = 65535 # prevent overflow
    return np.array(ret, dtype='uint16') 

'''
img: np array
borders: [minX, minY, maxX, maxY]
cirlce: (centreX, centreY, radius)
reqFlag: 0 if this was a user-requested image, else: 1 if shift = 10, 2 if shift = 0
'''

FLAG_OLD_WAY = True # False for experimental version (worse)
def correct_transversalium_legacy(img, circle, borders, options, reqFlag, basefich):
    if circle == (-1, -1, -1):
        print('ERROR : no circle fit so no transversalium correction')
        return img
    if (not (reqFlag == 1)) and not FLAG_OLD_WAY:
        c = options['_transversalium_cache']
    else:
        y_s = []
        y_mean = []
        y_mean_raw = []
        y1 = math.ceil(max(circle[1] - circle[2], borders[1]))
        y2 = math.floor(min(circle[1] + circle[2], borders[3]))

        sum_s = 0
        sum_s2 = 0
        count = 0
        for y in range(y1, y2):
            dx = math.floor((circle[2]**2 - (y-circle[1])**2)**0.5)
            strip = img[y, math.ceil(max(circle[0] - dx, borders[0])) : math.floor(min(circle[0] + dx, borders[2]))]
            count += strip.shape[0]
            sum_s += np.sum(strip)
            sum_s2 += np.sum(strip*strip)

        stdev = (sum_s2 / count - (sum_s / count) ** 2)**0.5
        print('disc_stdev:', stdev)
            

                
        for y in range(y1, y2):
            dx = math.floor((circle[2]**2 - (y-circle[1])**2)**0.5)
            strip = img[y, math.ceil(max(circle[0] - dx, borders[0])) : math.floor(min(circle[0] + dx, borders[2]))]

            y_s.append(y)
            y_mean.append(np.mean(reject_outliers(strip)))
            y_mean_raw.append(np.mean(strip))
            if y == 1040 or y == 900:
                plt.plot(strip)
                plt.title('strip')
                plt.show()
            if y == 1040 and 0:
                print(y)
                plt.hist(strip, bins = range(0, 2**16, 2**10))
                plt.hist(reject_outliers(strip), bins = range(0, 2**16, 2**10))
                plt.show()
                print('mean1,2: ', np.mean(strip), np.mean(reject_outliers(strip)))
                
        y_mean_raw = np.array(y_mean_raw)
        
        #fit_convex(y_mean_raw)
        #smoothed2 = savgol_filter(y_mean, min(301, len(y_mean) // 2 * 2 - 1), 3)
        smoothed = savgol_filter(y_mean, min(options['trans_strength'], len(y_mean) // 2 * 2 - 1), 3)
        
        plt.plot(y_s, y_mean, label = 'outlier-removed')
        plt.plot(y_s, y_mean_raw, label = 'raw')
        #plt.plot(y_s, smoothed2)
        plt.plot(y_s, smoothed, label = 'smoothed')
        plt.legend()
        plt.savefig(basefich+'_trans_curve.png')
        plt.show()
        plt.clf()
        
        
        correction = np.divide(smoothed, y_mean)
        a = 0.05 # taper width
        N = correction.shape[0]

        # Tukey taper function
        def t(x):
            if 0 <= x < a*N/2:
                return 1/2 * (1-math.cos(2*math.pi*x/(a*N)))
            elif a*N/2 <= x <= N/2:
                return 1
            elif N/2 <= x <= N:
                return t(N - x)
            print('error: weird input for taper function: ' + str(x))
            return 1

        taper = np.array([t(x) for x in range(N)])
        
        correction_t = np.ones(N) + (correction - np.ones(N)) * taper

        #plt.plot(y_s, correction)
        #plt.plot(y_s, correction_t)
        #plt.show()

        c = np.ones(img.shape[0])
        c[y1:y2] = correction_t
        #c[c<1] = 1
        options['_transversalium_cache'] = c
    if (reqFlag == 1 or (FLAG_OLD_WAY and not reqFlag)) and (not options['clahe_only']):
        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        ax.plot(c)
        ax.set_xlabel('y')
        ax.set_ylabel('transversalium correction factor')
        fig.savefig(basefich+'_transversalium_correction.png', dpi=300)
    ret = (img.T * c).T # multiply each row in image by correction factor
    ret[ret > 65535] = 65535 # prevent overflow
    return np.array(ret, dtype='uint16') 


def fit_convex(data):
    '''
    from scipy.optimize import lsq_linear
    data = - data
    n = data.shape[0]
    A = np.zeros((n, n), dtype = data.dtype)
    A[0, 0] = 1
    A[1, 1] = 1
    for i in range(2, n):
        A[i, :] = A[i - 1] * 2 - A[i - 2]
        A[i, i] = 1
    print(A)
    lb = np.zeros(n)
    lb[0] = -np.inf
    lb[1] = -np.inf
    ub = np.zeros(n)
    ub[:] = np.inf
    res = lsq_linear(A, data, bounds=(lb, ub), lsmr_tol='auto', verbose=1)
    print(res)
    plt.plot(A @ res.x)
    plt.plot(data)
    plt.show()
    '''
    def fit_func(x, m, a, b, c):
        return a*(x-m)**2 + b*(x-m)**4 + c

    x = np.arange(data.shape[0])

    p = np.polyfit(x, data, 2)
    
    
    popt, pcov = curve_fit(fit_func, x, data, p0 = [-p[1]/p[0]/2, p[0], 0, p[2] - p[1]**2/4/p[0]] )
    plt.plot(x, fit_func(x, *popt))
    plt.plot(x, data)
    plt.show()
    sub = data - fit_func(x, *popt)
    plt.plot(x, sub)
    plt.show()
    


def image_process(frame, cercle, options, header, basefich):
    flag_result_show = options['flag_display']
                
    # create a CLAHE object (Arguments are optional)
    # clahe = cv2.createCLAHE(clipLimit=0.8, tileGridSize=(5,5))
    clahe = cv2.createCLAHE(clipLimit=0.8, tileGridSize=(2,2))
    cl1 = clahe.apply(frame)
    
    # image leger seuils
    frame1=np.copy(frame)
    Seuil_bas=np.percentile(frame, 25)
    Seuil_haut=np.percentile(frame,99.9999)
    print('Seuil bas       :', np.floor(Seuil_bas))
    print('Seuil haut      :', np.floor(Seuil_haut))
    fc=(frame1-Seuil_bas)* (65535/(Seuil_haut-Seuil_bas))
    fc[fc<0]=0
    fc[fc>65535] = 65535
    frame_contrasted=np.array(fc, dtype='uint16')
    
    # image seuils serres 
    frame1=np.copy(frame)
    Seuil_bas=(Seuil_haut*0.25)
    Seuil_haut=np.percentile(frame1,99.9999)
    print('Seuil bas HC    :', np.floor(Seuil_bas))
    print('Seuil haut HC   :', np.floor(Seuil_haut))
    fc2=(frame1-Seuil_bas)* (65535/(Seuil_haut-Seuil_bas))
    fc2[fc2<0]=0
    fc2[fc2>65535] = 65535
    frame_contrasted2=np.array(fc2, dtype='uint16')
    
    # image seuils protus
    frame1=np.copy(frame)
    Seuil_bas=0
    Seuil_haut=np.percentile(frame1,99.9999)*0.18        
    print('Seuil bas protu :', np.floor(Seuil_bas))
    print('Seuil haut protu:', np.floor(Seuil_haut))
    fc2=(frame1-Seuil_bas)* (65535/(Seuil_haut-Seuil_bas))
    fc2[fc2<0]=0
    fc2[fc2>65535] = 65535
    frame_contrasted3=np.array(fc2, dtype='uint16')
    if not cercle == (-1, -1, -1) and options['disk_display']:
        x0=int(cercle[0])
        y0=int(cercle[1])
        r=int(cercle[2]) + options['delta_radius']
        if r > 0:
            frame_contrasted3=cv2.circle(frame_contrasted3, (x0,y0),r,80,-1)            
    Seuil_bas=np.percentile(cl1, 10)
    Seuil_haut=np.percentile(cl1,99.9999)*1.05
    cc=(cl1-Seuil_bas)*(65535/(Seuil_haut-Seuil_bas))
    cc[cc<0]=0
    cc[cc>65535] = 65535
    cc=np.array(cc, dtype='uint16')

    # handle rotations
    cc = np.rot90(cc, options['img_rotate']//90, axes=(0,1))
    frame_contrasted = np.rot90(frame_contrasted, options['img_rotate']//90, axes=(0,1))
    frame_contrasted2 = np.rot90(frame_contrasted2, options['img_rotate']//90, axes=(0,1))
    frame_contrasted3 = np.rot90(frame_contrasted3, options['img_rotate']//90, axes=(0,1))
    frame = np.rot90(frame, options['img_rotate']//90, axes=(0,1))
    
    # sauvegarde en png de clahe
    cv2.imwrite(basefich+'_clahe.png',cc)   # Modification Jean-Francois: placed before the IF for clear reading
    if not options['clahe_only']:
        # sauvegarde en png pour appliquer une colormap par autre script
        #cv2.imwrite(basefich+'_disk.png',frame_contrasted)
        # sauvegarde en png pour appliquer une colormap par autre script
        cv2.imwrite(basefich+'_diskHC.png',frame_contrasted2)
        # sauvegarde en png pour appliquer une colormap par autre script
        cv2.imwrite(basefich+'_protus.png',frame_contrasted3)
    
    # The 3 images are concatenated together in 1 image => 'Sun images'
    # The 'Sun images' is scaled for the monitor maximal dimension ... it is scaled to match the dimension of the monitor without 
    # changing the Y/X scale of the images 
    if flag_result_show:
        im_3 = cv2.hconcat([cc, frame_contrasted2, frame_contrasted3])
        screen = tk.Tk()
        screensize = screen.winfo_screenwidth(), screen.winfo_screenheight()
        screen.destroy()
        scale = min(screensize[0] / im_3.shape[1], screensize[1] / im_3.shape[0]) * 0.9
        cv2.namedWindow('Sun images', cv2.WINDOW_NORMAL)
        cv2.moveWindow('Sun images', 0, 0)
        cv2.resizeWindow('Sun images',int(im_3.shape[1] * scale), int(im_3.shape[0] * scale))
        cv2.imshow('Sun images',im_3)
        cv2.waitKey(options['tempo'])  # affiche et continue
        cv2.destroyAllWindows()

    frame2=np.copy(frame)
    frame2=np.array(cl1, dtype='uint16')
    # sauvegarde le fits
    if options['save_fit']:
        DiskHDU=fits.PrimaryHDU(frame2,header)
        DiskHDU.writeto(basefich+ '_clahe.fits', overwrite='True')
