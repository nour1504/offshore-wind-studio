"""One lock for every NetCDF (HDF5) access of the process.

The netCDF-C and HDF5 of the netCDF4 wheels are not thread-safe and the server answers in several
threads: two files read at once can crash the process (an access violation, seen on Windows). Every
open, read and close holds this lock, through netCDF4 or xarray.
"""

import threading

LOCK = threading.RLock()
