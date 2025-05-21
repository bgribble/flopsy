

# build with 'python ./setup.py install'
from distutils.core import setup

VERSION = "0.0.7"

setup(
    name = 'flopsy',
    version = VERSION,
    license = 'MIT',
    description = 'Redux-inspired state management',
    author = 'Bill Gribble',
    author_email = 'grib@billgribble.com',
    url = 'https://github.com/bgribble/flopsy',
    download_url = f'https://github.com/bgribble/flopsy/archive/refs/tags/v{VERSION}.tar.gz',
    keywords = ['state-management', 'redux', 'saga'],
    install_requires = [
        'pyopengl', 'glfw', 'imgui_bundle>=1.6.3',
    ],
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'License :: OSI Approved :: MIT License',
    ],
)
