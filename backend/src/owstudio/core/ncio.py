"""One lock for every NetCDF (HDF5) access of the process.

The netCDF-C and HDF5 libraries shipped with the netCDF4 wheels are not built thread-safe, and
the server answers requests in several threads: two files opened or read at the same time can
crash the whole process (an access violation, seen on Windows with the checks and the input
examination running together). Every open, read and close of a NetCDF file holds this lock,
whether through netCDF4 directly or through xarray.
"""

import threading

LOCK = threading.RLock()
