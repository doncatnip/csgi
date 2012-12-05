from setuptools import setup, find_packages

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
    , include_package_data = True
    , install_requires = [ "gevent", "python-daemon" ]
    , classifiers =\
        [ "Development Status :: 3 - Alpha"
        , "Intended Audience :: Developers"
        , "Topic :: Software Development :: Libraries :: Python Modules"
        , "Topic :: System :: Networking"
        , "License :: Public Domain"
        , "Programming Language :: Python :: 2.7"
        ]
    )
