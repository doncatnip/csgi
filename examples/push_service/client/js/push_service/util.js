define
  ( 'app/util'
  , [ 'dojo/_base/lang'
    , 'dojo/_base/Deferred'
    ]
  , function( lang, defer ) {

      defer.all = function( deferreds, callback, context) {
        var results = [];
        var busy = deferreds.length;
        for (var i=0;i<deferreds.length;i++) {
          results.push( null );
          (function( ii ) {
            defer.when
              ( deferreds[ii]
              , function( r ) {
                  results[ii] = r;
                  busy-=1;
                  if (!busy)
                    callback.apply( context, results );
                }
              );
          })(i); /*iife to keep i*/
        }
      };
      return {
        bind:
          function( source, name, target, target_name ) {
            var targetIsFunction = target_name
              && target_name !== undefined
              && typeof target_name == "function";
          
            var target_value;
            if (targetIsFunction) {
              if (target) {
                target = lang.hitch( target, target_name );
              } else {
                target = target_name;
              }
            } else {
              target_name = target_name || name;
            }
          
            if (!targetIsFunction) {
              if (source.get(name) != target.get( target_name ) ) {
                target.set( target_name, source.get(name) );
              }
            } else if( source.get(name) )
              target( source.get(name), name );
          
            var watcher = source.watch( name, function( prop, oldValue, newValue ) {
              if (!targetIsFunction) {
                if (newValue != target.get( target_name )) {
                  target.set( target_name, newValue );
                }
              } else
                target( newValue, name );
            });
          
            watcher.cancel = watcher.unwatch;
            return watcher;
          }
        };
     });

