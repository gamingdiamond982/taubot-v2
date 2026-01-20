# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2])+'/src')

project = 'Taubot V2 Documentation'
copyright = '2025, Some Stoner'
author = 'Some Stoner'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.githubpages',
    'sphinxcontrib.httpdomain',
    'sphinxext.opengraph'
]

templates_path = ['_templates']
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'pydata_sphinx_theme'
html_static_path = ['_static']
html_show_sourcelink = False
html_theme_options = {
  'collapse_navigation': True,
  'logo': {
    'text': 'Taubot V2 Documentation',
   }
}
html_sidebars = {
  '**': []
}
html_favicon = '_static/favicon.png'
html_logo = '_static/logo.png'

# -- Options for Oembed ------------------------------------------------------
# https://sphinxext-opengraph.readthedocs.io/en/latest/#options

ogp_site_url = "https://docs.tau.work.gd"
ogp_image = "_static/logo.png"
ogp_custom_meta_tags = [
    '<meta property="og:ignore_canonical" content="true" />',
    '<meta name="theme-color" content="#e8cc4c" />'
]
ogp_enable_meta_description = True