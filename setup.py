# Always prefer setuptools over distutils
from setuptools import setup, find_packages
from glob import glob

setup(
    name="catplotlib",
    version="3.6.3",
    description="catplotlib",
    long_description="catplotlib",
    url="",
    author="Moja.global",
    author_email="",
    license="MPL2",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: Mozilla Public License 2.0",
        "Programming Language :: Python :: 3",
    ],
    keywords="moja.global",
    packages=find_packages(exclude=["contrib", "docs", "tests"]),
    install_requires=[
        "sqlalchemy", "psutil",
        "numpy", "seaborn", "imageio", "imageio-ffmpeg",
        "pillow", "geopy", "utm", "jupyter-book", "sphinxcontrib-bibtex",
        "aenum", "pyepsg", "pyppeteer", "plotly",
        "pysal<=1.15.0; python_version=='3.7'", "pysal; python_version>'3.7'",
        "mojadata>=4.0.6",
        "shapely>=1.8.1, <=1.8.2", # cartopy (any ver) requires this version of shapely
        "matplotlib==3.5.2; python_version=='3.7'", "matplotlib; python_version>'3.7'", # cartopy < 0.21 requires matplotlib 3.5.2
        "cartopy==0.18.0; python_version=='3.7'", "cartopy; python_version>'3.7'",
        "pyproj==3.2.1; python_version=='3.7'", "pyproj; python_version>'3.7'",
    ],
    extras_require={},
    package_data={},
    data_files=[
        ("Tools/catplotlib/locales/en/LC_MESSAGES", glob("files/locales/en/LC_MESSAGES/*")),
        ("Tools/catplotlib/locales/fr/LC_MESSAGES", glob("files/locales/fr/LC_MESSAGES/*")),
        ("Tools/catplotlib/catanimate", ["files/catanimate/indicators.json"]),
        ("Tools/catplotlib/catanimate/examples", [
            "files/examples/calculate_ghg.py",
            "files/catanimate/examples/create_bc_animation.py",
            "files/catanimate/examples/disturbance_colors.json",
            "files/catanimate/examples/interpreted_indicators.json"
        ]),
        ("Tools/catplotlib/catreport/templates/basic_gcbm",     glob("files/catreport/templates/basic_gcbm/*")),
        ("Tools/catplotlib/catreport/templates/multipage_gcbm", glob("files/catreport/templates/multipage_gcbm/*")),
        ("Tools/catplotlib/catreport/templates/tabbed_gcbm",    glob("files/catreport/templates/tabbed_gcbm/*")),
    ],
    entry_points={
        "console_scripts": [
            "catanimate = catplotlib.scripts.catanimate:cli",
            "catreport = catplotlib.scripts.catreport:cli",
            "catoverlay = catplotlib.scripts.catoverlay:cli",
            "catsummarize = catplotlib.scripts.catsummarize:cli",
        ]
    },
    python_requires=">=3.7"
)