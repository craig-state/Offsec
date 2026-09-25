from setuptools import setup, find_packages
from . import _entry

setup(
    name="megacorpone-ai-toolkit",
    version="1.4.2",
    description="MegaCorpOne AI Engineering Toolkit - Model sync, API client, and configuration utilities",
    author="MegaCorpOne AI Engineering",
    author_email="ai-engineering@megacorpone.com",
    packages=find_packages(),
    install_requires=[
        "requests>=2.28.0",
        "pyyaml>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "megacorpone-sync=megacorpone_ai_toolkit.sync:main",
        ],
    },
    python_requires=">=3.9",
)
