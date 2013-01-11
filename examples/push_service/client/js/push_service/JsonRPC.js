define( ['dojo/_base/json', "dojox", "dojox/rpc/Service" ], function(json, dojox) {

  function jsonRpcEnvelope(version){
    return {
      serialize: function(smd, method, data, options){
        //not converted to json it self. This  will be done, if
        //appropriate, at the transport level
        var d = {
          id: this._requestId++,
          method: method.name,
          params: data[0] || []
        };
        if(version){
          d.jsonrpc = version;
        }
        return {
          data: json.toJson(d),
          handleAs: 'json',
          contentType: 'application/json',
          transport: "POST"
        };
      },
      deserialize: function(obj){
        var err;
        if (obj===null || obj===undefined) {
          err = new Error( 'Cancelled' );
          err.requestCancelled = true;
          return err;
        }

        if ('Error' == obj.name){
          if (obj.status!=200) {
            err = new Error( 'Server Error' );
            err.serverError = obj.status;
            return err;
          }

          obj = json.fromJson(obj.responseText);
        }
        if(obj.error) {
          var e = new Error(obj.error.message || obj.error);
          e._rpcErrorObject = obj.error;
          return e;
        }
        return obj.result;
      }
    };
  }

  dojox.rpc.envelopeRegistry.register(
    "JSON-RPC-2.0",
    function(str){
      return str == "JSON-RPC-2.0";
    },
    jsonRpcEnvelope("2.0")
  );

});
