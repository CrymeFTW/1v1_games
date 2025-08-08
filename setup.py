from pathlib import Path
from setuptools import setup, find_packages

README = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="lan-battleship",
    version="0.1.0",
    description="Two-player Battleship over LAN (GUI)",
    long_description=README,
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=("tests", "docs", "examples")),
    python_requires=">=3.9",
    install_requires=[
        "pygame>=2.5.0",
    ],
    entry_points={
        "console_scripts": [
            "battleship=battleship.gui:run_host_gui_main",
            "battleship-host=battleship.gui:run_host_gui_main",
            "battleship-join=battleship.gui:run_client_gui_main",
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
