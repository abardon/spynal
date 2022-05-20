#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Functions for loading from and saving to Matlab MAT files

Function list
-------------
- loadmat : Loads variables from any Matlab MAT file. Also aliased as 'load'.
- savemat : Saves given variables into a MAT file. Also aliased as 'save'.
- whomat :  Lists all variables in any MAT file. Also aliased as 'who'.

Dependencies
------------
- h5py :    Python interface to the HDF5 binary data format (used for mat v7.3 files)

Function reference
------------------
"""
# Created on Mon Mar 12 17:20:26 2018
#
# @author: sbrincat
import sys
from copy import deepcopy
import numpy as np
import pandas as pd

from spynal.matIO.matIO_7 import _load7, _who7, _save7
from spynal.matIO.matIO_73 import _load73, _who73
from spynal.matIO.helpers import _parse_typemap, _get_matfile_version, _variables_to_mat


# =============================================================================
# Matfile loading/introspection functions
# =============================================================================
def loadmat(filename, variables=None, typemap=None, asdict=False, order='Matlab', verbose=True):
    """
    Load variables from a given MAT file and return them in appropriate Python types

    Handles both older (v4-v7) and newer (v7.3) versions of MAT files,
    transparently to the user.

    Variables returned individually or in a dict, where each variable maps to key/value pair

    Returned variable types are logical Python equivalents of Matlab types:
    ======              ======
    MATLAB              PYTHON
    ======              ======
    double/single       float
    int                 int
    char,string         str
    logical             bool
    array               Numpy ndarray of appropriate dtype
    cell array          Numpy ndarray of object dtype
    struct              dict or Pandas Dataframe (for table-like structs; depends on typemap)
    ======              ======

    Single-element Matlab arrays are converted to the contained item type (eg float/int/str)

    NOTE: Some proprietary or custom Matlab variables cannot be loaded, including:
    table/timetable, datetime, categorical, function_handle, map container, any custom object class

    Parameters
    ----------
    filename : str
        Full-path name of MAT file to load from

    variables : list of str, default: <all variables in file>
        Names of all variables to load

    typemap : dict {str:str}, default: {'array':'array', 'cell':'array', 'struct':'dict'}
        Maps names of Matlab variables or variable types to returned Python variable types.
        Currently alternative options only supported for table-like structs, which can
        return either as 'dict' or 'dataframe' (Pandas DataFrame).

    asdict : bool, default: False
        If True, returns variables in a {'variable_name':value} dict.
        If False, returns variables separately (as tuple).

    order : str, default: 'Matlab'
        Dimension order of returned arrays. Determines how values are arranged when reshaped.
        Options:
        - 'Matlab'/'F'  : Use Matlab/Fortran dimensional ordering (column-major-compatible)
        - 'Python'/'C'  : Use Python/C dimensional ordering (row-major compatible)

    verbose : bool, default: True
        If True, prints names and shapes of all loaded variables to stdout

    Returns
    -------
    data_dict : dict {str:<variable>}
        Dictionary holding all loaded variables, mapping variable name to its value

    -or-

    vbl1,vbl2,... :
        Variables returned individually, as in 2nd example above

    Examples
    --------
    data_dict = loadmat(filename, variable, asdict=True)

    variable1, variable2, ... = loadmat(filename, variable, asdict=False)
    """
    # If variables input as string, convert to list
    if isinstance(variables,str):  variables = [variables]

    # Combine any input values for typemap with defaults
    typemap = _parse_typemap(typemap)

    assert order.upper() in ['MATLAB','F','COL','COLMAJOR','PYTHON','C','ROW','ROWMAJOR'], \
        "<order> must be 'Matlab' or 'Python' (%s given)" % order

    version = _get_matfile_version(filename)

    # Use h5py to load v7.3 MAT-files (which are a type of hdf5 file)
    if version == 7.3:  data = _load73(filename,variables,typemap,order)

    # Use scipy.io.loadmat() to load v7 and older MAT-files
    else:               data = _load7(filename,variables,typemap,order)

    if variables is None: variables = list(data.keys())

    if verbose:
        for vbl in variables:
            if isinstance(data[vbl], np.ndarray):       # Numpy array variables
                vblstr = vbl + ' : numpy.array(' + \
                        ''.join('%3d,' % x for x in data[vbl].shape) + ')' + \
                        (' of type %s' % data[vbl].dtype)
            elif isinstance(data[vbl], pd.DataFrame):   # Pandas DataFrame variables
                vblstr = vbl + ' : pandas.DataFrame with columns[' + \
                        ''.join('%s,' % x for x in data[vbl].keys()) + ']'
            elif isinstance(data[vbl], dict):           # dict variables (Matlab structs)
                vblstr = vbl + ' : dict with keys[' + \
                        ''.join('%s,' % x for x in data[vbl].keys()) + ']'
            else:                                       # Scalar variables (float/int/string)
                vblstr = vbl
            vblstr = vblstr + '\n'
            print(vblstr)

    if asdict:                  return data
    elif len(variables) == 1:   return data[variables[0]]
    else:                       return tuple(data[vbl] for vbl in variables)

load = loadmat
""" Alias of :func:`loadmat`. See there for details. """


def whomat(filename, verbose=True):
    """
    Return list of variables in a given MAT file and/or print them to stdout

    Parameters
    ----------
    filename : str
        Full-path name of MAT-file to examine

    verbose : bool, default: True
        If True, prints names of all file variables to stdout

    Returns
    -------
    variables : list of str
        Names of variables in file
    """
    version = _get_matfile_version(filename)

    # Use h5py to load v7.3 MAT-files (which are a type of hdf5 file)
    if version == 7.3:  variables = _who73(filename)

    # Use scipy.io.loadmat() to load v7 and older MAT-files
    else:               variables = _who7(filename)

    if verbose: print(variables)

    return variables

who = whomat
""" Alias of :func:`whomat`. See there for details. """


# =============================================================================
# Matfile saving functions
# =============================================================================
def savemat(filename, variables, version=None, **kwargs):
    """
    Save data variables to a Matlab MAT file

    NOTE: Currently can only save older (v7), not newer (v7.3), versions of MAT files

    Parameters
    ----------
    filename : str
        Full-path name of MAT file to save to

    variables : dict {str:<variable>}
        Names and values of variables to save

    version : float, default: (7.3 if any variable is > 2 GB; 7 otherwise)
        Version of MAT file: 7 (older) | 7.3 (newer/HDF5).

    **kwargs
        All other keyword args passed to scipy.io.savemat()
    """
    assert (version is None) or (version in [7,7.3]), ValueError("version must be 7 or 7.3")

    # Do any necessary conversions to get all variables into matfile-compatible format
    # Note: Use deepcopy to create copy of all variables to avoid changing in caller
    variables = _variables_to_mat(deepcopy(variables))

    # If version is not set or set=7, check to make sure no variables are > 2 GB
    if version != 7.3:
        # Compute max size in memory of any variable (in GB)
        sizes = [sys.getsizeof(variables[vbl]) for vbl in variables.keys()]
        max_size = np.max(np.asarray(sizes))/(1024.0**3)
        # If any veriable is > 2GB, must use v7.3, otherwise default to v7
        if max_size >= 2:
            if version == 7: print('WARNING: Variable > 2 GB, switching to MAT file v7.3')
            version = 7.3
        else:
            version = 7

    # Use hdf5storage to save v7.3 MAT-files (which are a type of hdf5 file)
    if version == 7.3:
        raise ValueError('Saving MAT file version 7.3 not coded up yet')

    # Use scipy.io.savemat() to save v7 MAT-files
    else:
        _save7(filename, variables, **kwargs)

save = savemat
""" Alias of :func:`savemat`. See there for details. """


# Setup so module can be run from command line using:  python matIO.py <arguments>
if __name__ == "__main__":
    loadmat(sys.argv[1])
