@echo off
set PYTHONHOME=c:\python37

if exist dist rd /s /q dist

for /d %%d in (files\locales\*) do (
	python %PYTHONHOME%\tools\i18n\msgfmt.py -o %%d\LC_MESSAGES\catplotlib.mo %%d\LC_MESSAGES\catplotlib.po
)

python -m pip install --upgrade setuptools wheel
python setup.py bdist_wheel
if exist build rd /s /q build
if exist catplotlib.egg-info rd /s /q catplotlib.egg-info
