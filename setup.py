from setuptools import setup, find_packages
import os

version = '1.3dev'

setup(name='poi.receivemail',
      version=version,
      description="Receive email in the Poi issue tracker",
      long_description=open("README.txt").read() + "\n" +
                       open(os.path.join("docs", "HISTORY.txt")).read(),
      # Get more strings from
      # http://pypi.python.org/pypi?:action=list_classifiers
      classifiers=[
        "Framework :: Plone",
        "Programming Language :: Python",
        ],
      keywords='',
      author='Maurits van Rees',
      author_email='maurits@vanrees.org',
      url='http://svn.plone.org/svn/collective/poi.receivemail',
      license='GPL',
      packages=find_packages(exclude=['ez_setup']),
      namespace_packages=['poi'],
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'setuptools',
      ],
      entry_points="""
      # -*- Entry points: -*-

      [z3c.autoinclude.plugin]
      target = plone
      """,
      )
