define
  ( [ 'dojo/_base/declare'
    , 'dojo/_base/config'
    , 'dijit/form/Form'
    , 'dijit/_WidgetsInTemplateMixin'
    , 'dojo/text!app/view/login.html'
    , 'dijit/form/Button'
    , 'dijit/form/ValidationTextBox'
    ]
    , function( declare, config, Form, WidgetsInTemplate, template  ) {

        return declare
          ( 'app.LoginStatus'
          , [ Form, WidgetsInTemplate ]
          , { templateString: template
            , postCreate: function() {
                this.inherited( arguments );
              }
            , onSubmit: function( user ) {
                if (this.validate()) {
                  config.app.remoteApi.login( this.getValues() );
                  return true;
                }
                return false;
              }
            }
          );
    });

