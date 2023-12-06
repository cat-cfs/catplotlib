@echo off

set GCBM_PYTHON=C:\Python310
set GDAL_BIN=%GCBM_PYTHON%\lib\site-packages\osgeo
set GDAL_DATA=%GDAL_BIN%\data\gdal
set PROJ_LIB=%GDAL_BIN%\data\proj
set PYTHONPATH=%GCBM_PYTHON%;%GCBM_PYTHON%\lib\site-packages
set "PATH=%GCBM_PYTHON%;%GDAL_BIN%;%GDAL_DATA%;%GCBM_PYTHON%\scripts;%GCBM_PYTHON%\lib\site-packages;C:\Program Files\MiKTeX\miktex\bin\x64;%PATH%"

set "TITLE=GCBM_Results_%date:~0,4%_%date:~5,2%_%date:~8,2%
set "TITLE=%TITLE: =0%"

jb clean . && jb build . --builder pdflatex && copy _build\latex\python.pdf %TITLE%.pdf
