from setuptools import setup, find_packages

version = '1.11dev'

setup(name='poi.receivemail',
      version=version,
      description="Receive email in the Poi issue tracker",
      long_description=open("README.txt").read() + "\n" +
                       open("CHANGES.rst").read(),
      # Get more strings from
      # http://pypi.python.org/pypi?:action=list_classifiers
      classifiers=[
        "Framework :: Plone",
        "Framework :: Plone :: 3.2",
        "Framework :: Plone :: 3.3",
        "Framework :: Plone :: 4.0",
        "Framework :: Plone :: 4.1",
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
