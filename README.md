csgi - client/server gateway interface
======================================

I'm writing this, because im tired of the common practice today to
tightly couple the http transport into the wsgi servers and making various
bidirectional protocols dependand on wsgi - reducing their flexibility and
counteracting DRY.

WSGI really should be only a handler ontop of a HTTP transport.

The idea goes as followes: find an wsgi-ish way to bubble a connection
( which eventually might become a request) from the very bottom ( the listener )
all the way up to some handler ( which could be a html page, or an amqp
subscriber/publisher ).

Every transport receives ( env, socket ) per connection as arguments and
passes a read and write method to its handler while populating env with
transport-specific stuff.

read is a callable which returns a list or generator, write is a callable,
receiving one argument.

A request/connection is considered finished when its handler returns.

Status: prototype 
License: Public Domain
