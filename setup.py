# Always prefer setuptools over distutils
from setuptools import setup, find_packages
from glob import glob

setup(
    name="catplotlib",
    version="1.11",
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
        "numpy", "matplotlib", "seaborn", "imageio", "imageio-ffmpeg",
        "pillow", "geopy", "pysal<=1.15.0", "utm", "jupyter-book",
        "plotly", "sphinxcontrib-bibtex<2.0.0", "pyppeteer", "cartopy",
        "aenum", "pyepsg"
    ],
    extras_require={},
    package_data={},
    data_files=[
        ("Tools/catplotlib/catanimate", ["files/catanimate/indicators.json"]),
        ("Tools/catplotlib/catanimate/examples", [
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
            "catreport = catplotlib.scripts.catreport:cli"
        ]
    },
    python_requires=">=3.7"
)