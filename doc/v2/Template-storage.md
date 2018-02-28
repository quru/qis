QIS v2.0 Move image templates from text files into the database
===============================================================

Current status: complete

Add Template model class:

* name (lower case, unique index)     } one field using function index?
* displayname (user's own case)       }
* description
* template (json)
* last changed date? by who?

Using the Postgres JSON type requires Postgres 9.2 or above.

(With a displayname for templates, we could do with the same for ICC profiles,
 which are currently all lower case in the UI, not ideal)

Storing template data as JSON means we can add/remove image fields without breaking
existing templates. We'll lose the comments in the template files so ensure the
comments are documented in the help file.

(We have a description field for the template, but would users like (to retain)
 the ability to store per-field comments in the template?)

Add a template manager to list/get/set/delete templates. Validation function too.  
Template manager to call data manager and cache templates internally.  
Template manager cache to be invalidated when a template is updated/deleted.  
Add templates to data API, API to call template manager.  
API to report validation failures on add/update.  

Existing image publish page does most of what we need for defining a template.  
Having a preview is nice for some fields.  
Tweaks required, e.g. hiding the template field, html output.  
May be best to have a new admin page but refactor+re-use common components.  
