"""Build hook: copy the scenarios, trials, load bundles, Context set, split lists and run configs into
the package as whowins/_bundle, so an installed package runs without a checkout (whowins.data reads the
checkout when there is one). MANIFEST.in puts the same files in the sdist. Everything else is in
pyproject.toml."""
import glob
import os
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED = ["data/scenarios/*/*.json", "data/trials/*.json", "data/load/*.json", "data/realism/*.json",
           "data/splits/*.json", "configs/*.json", "configs/runs/*.json", "configs/vllm/*.yaml",
           "configs/chat-templates/*.jinja"]


class BuildWithData(build_py):
    """The usual build, then the data and configs under whowins/_bundle."""

    def run(self):
        super().run()
        for pattern in BUNDLED:
            for path in sorted(glob.glob(os.path.join(HERE, pattern))):
                dest = os.path.join(self.build_lib, "whowins", "_bundle", os.path.relpath(path, HERE))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copyfile(path, dest)


setup(cmdclass={"build_py": BuildWithData})
