from gevent import sleep, spawn
from datetime import datetime

from uuid import uuid4 as uuid

from settings import db
import lib
import logging

log = logging.getLogger( __name__ )

profile_channels = {}
guest = { 'name': 'guest', 'role': 'guest', '_id': '0' }

def pinger( channel ):
    while True:
        sleep( 60 )
        channel.emit( ('ping',datetime.utcnow() ) )

class push:

    @staticmethod
    def ping( env, channel ):
        p = spawn( pinger, channel )
        channel.on_close( p.kill )

    @staticmethod
    def user_profile( env, channel ):
        session = lib.get_session( env )
        user = db.user.find_one( {'session': session } )

        if user:
            del user['password']
        else:
            user = guest

        user['_id'] = str(user['_id'])
        channel.emit( ('update',user) )
        profile_channels[ session ] = channel
        channel.on_close( lambda: profile_channels.pop( session ) )

class api:

    @staticmethod
    def login( env, name, password ):
        session = lib.get_session( env )

        user = db.user.find_and_modify\
            ( {'name': name, 'password': password, 'session': {'$ne': session} }
            , {'$set': {'session': session } }
            , new=True
            )

        if user:
            user['_id'] = str(user['_id'])
            profile_channels[ session ].emit( ('update',user) )

    @staticmethod
    def logout( env ):
        session = lib.get_session( env )

        user = db.user.find_and_modify\
            ( {'session': session}
            , {'$unset': {'session': True } }
            )

        if user:
            profile_channels[ session ].emit( ('update',guest) )

    @classmethod
    def register( cls, env, name, password, email ):
        session = lib.get_session( env )

        db.user.insert\
            ( { 'name': name
              , 'password': password
              , 'email': email
              , 'role': 'user'
              }
            , safe=True
            )

        return cls.login( env, name, password )


    @staticmethod
    def update_profile( env, email, name ):
        session = lib.get_session( env )
        log.debug("email: %s, name: %s" % (email, name))

        user = db.user.find_and_modify\
            ( { 'session': session }
            , { '$set':
                  { 'email': email
                  , 'name': name
                  }
                
              }
            , new=True
            )

        if user:
            del user['password']
            user['_id'] = str(user['_id'])
            profile_channels[ session ].emit( ('update',user) )

