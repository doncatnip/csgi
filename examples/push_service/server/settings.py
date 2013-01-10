from pymongo import Connection

connection = Connection()
db = connection.csgi_push_service_example

db.user.ensure_index\
    ( 'name',1, unique=True )

db.user.ensure_index\
    ( 'email',1, unique=True )
