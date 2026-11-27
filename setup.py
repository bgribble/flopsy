"""Setup script for flopsy.

Build with 'python ./setup.py install' or 'pip install .'
"""
from pathlib import Path
from setuptools import setup, find_packages

# Read version from the package so there is a single source of truth.
import re
version_path = Path(__file__).parent / "flopsy" / "__init__.py"
with open(version_path, encoding="utf-8") as f:
    VERSION = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', f.read(), re.M).group(1)

# Read the long description from README.md.
readme_path = Path(__file__).parent / "README.md"
with open(readme_path, encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="flopsy",
    version=VERSION,
    license="MIT",
    description="Redux-inspired state management",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Bill Gribble",
    author_email="grib@billgribble.com",
    url="https://github.com/bgribble/flopsy",
    download_url=f"https://github.com/bgribble/flopsy/archive/refs/tags/v{VERSION}.tar.gz",
    project_urls={
        "Source": "https://github.com/bgribble/flopsy",
        "Issues": "https://github.com/bgribble/flopsy/issues",
    },
    keywords=["state-management", "redux", "saga"],
    python_requires=">=3.8",
    install_requires=[],  # core has no runtime dependencies
    extras_require={
        "inspector": [
            "pyopengl",
            "glfw",
            "imgui_bundle>=1.6.3",
            "sdl2",
        ],
        "dev": [
            "pytest",
            "pytest-asyncio",
        ],
    },
    packages=find_packages(exclude=["flopsy.test", "flopsy.test.*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
