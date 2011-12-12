from setuptools import setup, find_packages
from distutils.extension import Extension
from Cython.Distutils import build_ext

setup\
    ( name = 'csgi'
    , version = '0.0.0'
    , description = 'client/server gateway interface'
    , author = 'don`catnip'
    , author_email = 'don dot t at pan1 dot cc'
    , url = 'http://github.com/doncatnip/csgi'
    , license = 'Unlicense'
    , packages = find_packages('src')
    , package_dir = {'':'src'}
    , namespace_packages = ['csgi', 'csgi.http' ]
    , include_package_data = True
    , install_requires = [ "gevent" ]
    , cmdclass = {'build_ext': build_ext}
    , ext_modules = [Extension("csgi.http.ctransport", ["src/csgi/http/transport.c"])]
    , classifiers =\
        [ "Development Status :: 3 - Alpha"
        , "Intended Audience :: Developers"
        , "Topic :: Software Development :: Libraries :: Python Modules"
        , "Topic :: System :: Networking"
        , "License :: Public Domain"
        , "Programming Language :: Python :: 2.7"
        ]
    )
