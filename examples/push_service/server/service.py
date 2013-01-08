from gevent import sleep, spawn
from datetime import datetime

from pymongo import Connection
from uuid import uuid4 as uuid

connection = Connection()
db = connection.csgi_push_service_example

profile_channels = {}

def pinger( channel ):
    while True:
        sleep( 10 )
        channel.emit( ('ping',datetime.utcnow() ) )

class push:

    @classmethod
    def ping( env, channel ):
        p = spawn( pinger, channel )
        channel.on_disconnect( p.kill )

    @classmethod
    def userProfile( env, channel ):
        session = env['http']['request']['header'].get('cookie',{}).get('session')

        if session:
            user = db.user.find_one( {'session': session } )
            del user['password']
            channel.emit( user )

        profile_channels[ session ] = channel
        channel.on_disconnect( lambda: profile_channels.pop( session ) )

class api:

    @classmethod
    def login( env, name, password ):
        user = db.user.find_and_modify\
            ( {'name': name, 'password': password }
            , {'session': uuid() }
            , new=True
            )

        if user:
            return user['session']

    @classmethod
    def register( env, name, password, email ):
        db.user.insert( { 'name': name, 'password': password, 'email': email }, safe=True )
        return login( env, name, password )


    @classmethod
    def update_email( env, new_mail ):
        session = env['http']['request']['header'].get('cookie',{}).get('session')

        if session:
            user = db.user.find_and_modify\
                ( { 'session': session }
                , { 'email': new_mail }
                , new=True
                )
            profile_channels[ session ].emit( user )

