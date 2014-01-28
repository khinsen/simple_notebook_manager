#!/usr/bin/env python

from setuptools import setup, Command
import os

package_dir = "lib"
script_dir = "scripts"

with open('README.md') as file:
    long_description = file.read()
    long_description = long_description[:long_description.find("\n\n")]

setup(name='SimpleNotebookManager',
      version="0.1",
      description='A simple NotebookManager for IPython',
      long_description=long_description,
      author='Konrad Hinsen',
      author_email='konrad.hinsen@fastmail.net',
      url='http://github.com/khinsen/simple_notebook_manager',
      license='BSD',
      package_dir = {'': package_dir},
      modules=['simple_notebook_manager'],
      scripts=[os.path.join(script_dir, s) for s in os.listdir(script_dir)],
      platforms=['any'],
  )
