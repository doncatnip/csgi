define
  ( [ 'dojo/_base/declare'
    , 'dojo/_base/config'
    , 'dojo/_base/array'
    , 'dijit/form/Form'
    , 'dijit/_WidgetsInTemplateMixin'
    , 'dojo/text!app/view/update_profile.html'
    , 'dijit/form/ValidationTextBox'
    , 'dijit/form/Button'
    ]
    , function( declare, config, array, Form, WidgetsInTemplate, template ) {

        return declare
          ( 'app.UpdateProfile'
          , [ Form, WidgetsInTemplate ]
          , { templateString: template
            , postMixInProperties: function() {
                this.name = config.app.userManager.get("current").name;
                this.email = config.app.userManager.get("current").email;
                this.inherited( arguments );
              }
            , onSubmit: function() {
                this.inherited( arguments );
                if (this.validate()) {
                  config.app.remoteApi.update.profile( this.getValues() );
                  return true;
                }
                return false;
              }
            });
    });

