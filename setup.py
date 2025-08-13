from pathlib import Path
from setuptools import setup, find_packages

README = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="versus-games",
    version="0.1.0",
    description="Two-player LAN games (Battleship, Snake) with lobby selection",
    long_description=README,
    long_description_content_type="text/markdown",
    packages=find_packages(include=("versus", "versus.*")),
    python_requires=">=3.9",
    install_requires=[
        "pygame>=2.5.0",
    ],
    entry_points={
        "console_scripts": [
            "versus=versus.cli:main",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Games/Entertainment",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
