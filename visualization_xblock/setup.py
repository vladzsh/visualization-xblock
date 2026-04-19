"""Setup for visualization XBlock (Gemini-powered interactive simulations)."""

import os

from setuptools import setup


def package_data(pkg, roots):
    """Collect all files under ``roots`` as package data for ``pkg``."""
    data = []
    for root in roots:
        for dirname, _, files in os.walk(os.path.join(pkg, root)):
            for fname in files:
                data.append(os.path.relpath(os.path.join(dirname, fname), pkg))
    return {pkg: data}


setup(
    name="visualization-xblock",
    version="0.1.0",
    description="Open edX XBlock that generates interactive Gemini-powered simulations",
    license="AGPL v3",
    packages=["visualization"],
    install_requires=[
        "XBlock",
    ],
    entry_points={
        "xblock.v1": [
            "visualization = visualization:VisualizationXBlock",
        ]
    },
    package_data=package_data("visualization", ["static"]),
)
