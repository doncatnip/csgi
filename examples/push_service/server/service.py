from gevent import sleep, spawn
from datetime import datetime

from uuid import uuid4 as uuid

from settings import db
import lib
import logging

log = logging.getLogger( __name__ )

guest = { 'name': 'guest', 'role': 'guest', '_id': '0' }

profile_channels = {}
def push_user( session, user ):
    user['_id'] = str(user['_id'])
    if 'password' in user:
        del user['password']

    for channel in profile_channels[ session ]:
        channel.emit( ('update',user) )

def remove_channel( session, channel ):
    profile_channels[ session ].remove( channel )
    if not profile_channels[ session ]:
        del profile_channels[ session ]

def add_channel( session, channel ):
    channels = profile_channels.get( session )
    if not channels:
        profile_channels[ session ] = channels = set()

    channels.add( channel )

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

        add_channel( session, channel )
        user = db.user.find_one( {'session': session } )

        if user:
            del user['password']
        else:
            user = guest

        push_user( session, user )
        channel.on_close( remove_channel, session, channel )

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
            push_user( session, user )

    @staticmethod
    def logout( env ):
        session = lib.get_session( env )

        user = db.user.find_and_modify\
            ( {'session': session}
            , {'$unset': {'session': True } }
            )

        if user:
            push_user( session, guest )

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
            push_user( session, user )
