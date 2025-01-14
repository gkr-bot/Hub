import os
import re
import versioneer

from setuptools import find_packages, setup

project_name = "package-hub-test"


this_directory = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(this_directory, "hub/requirements/common.txt")) as f:
    requirements = f.readlines()

with open(os.path.join(this_directory, "hub/requirements/tests.txt")) as f:
    tests = f.readlines()

with open(os.path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name=project_name,
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description="demo",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="activeloop.ai",
    author_email="support@activeloop.ai",
    packages=find_packages(),
    install_requires=requirements,
    tests_require=tests,
    include_package_data=True,
    zip_safe=False,
    entry_points={"console_scripts": ["activeloop = hub.cli.commands:cli"]},
    setup_requires=[],
    dependency_links=[],
    project_urls={
        "Documentation": "https://demo.ai/",
        "Source": "https://github.com/gkr-bot/Hub",
    },
)
