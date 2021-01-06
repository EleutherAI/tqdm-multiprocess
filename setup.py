import setuptools
import os
from io import open as io_open

src_dir = os.path.abspath(os.path.dirname(__file__))

with open("README.md", "r") as fh:
    long_description = fh.read()

# Build requirements
extras_require = {}
requirements_dev = os.path.join(src_dir, 'requirements-dev.txt')
with io_open(requirements_dev, mode='r') as fd:
    extras_require['dev'] = [i.strip().split('#', 1)[0].strip()
                             for i in fd.read().strip().split('\n')]

# Get version from tqdm/_version.py
# __version__ = None
# src_dir = os.path.abspath(os.path.dirname(__file__))
# version_file = os.path.join(src_dir, '_version.py')
# with io_open(version_file, mode='r') as fd:
#     exec(fd.read())

install_requires = ["tqdm", "colorama"]

setuptools.setup(
    name="tqdm-multiprocess",
    version="0.0.11",
    author="researcher2",
    author_email="2researcher2@gmail.com",
    description="Easy multiprocessing with tqdm and logging redirected to main process.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/EleutherAI/tqdm-multiprocess",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],

    python_requires='>=3.6',
    extras_require=extras_require,
    install_requires=install_requires,
    packages=['tqdm_multiprocess'] + ['tqdm.' + i for i in setuptools.find_packages('tqdm')],
    package_data={'tqdm_multiprocess': ['LICENCE', 'examples/*.py','requirements-dev.txt']},
)
