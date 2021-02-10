@echo off
if exist dist rd /s /q dist
python -m pip install --upgrade setuptools wheel
python setup.py bdist_wheel
if exist build rd /s /q build
if exist catplotlib.egg-info rd /s /q catplotlib.egg-info
