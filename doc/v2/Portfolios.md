Portfolios
==========

Current status: pending

A portfolio is a hand-curated list of images that can be viewed together, downloaded
together, or transformed together (e.g. resized to the same dimensions, or having
a standard watermark applied). A portfolio may be viewed as a virtual folder,
although it will not have a folder path and sub-folders will not be allowed. It will
be possible to set the order of images in the portfolio and to override the filenames
of individual images. It will also be possible to apply imaging operations to
individual images, for example to crop an image specifically for the portfolio.

When the whole portfolio is made available for download, the payload will be a single
zip file, generated as a background task. Once generated, and if permissions allow,
the zip file will be downloadable from a non-guessable URL. The zip file and download
URL will have an expiry date. We may also require a limit on the total amount of disk
space that can be taken up by historic zip archives.

The export of a portfolio for download will require a manual "publishing" stage,
initiated by the portfolio owner or a folio administrator, using either the QIS
admin interface or the API. It will not be possible for other users to initiate
the creation of a zip file, even if they are authorised to view the portfolio.

A single portfolio may be published multiple times, e.g. once with the full size
original files, and again with reduced size thumbnails. Where there are image-level
transformations such as cropping, the portfolio-level transformations will be applied
on top.

If a portfolio is changed after being published, the associated zip files will not
updated automatically. The UI can inform the user when this situation occurs.

An audit trail will be recorded for portfolios. This will record portfolio creation
and update times (and the file paths of images added and removed). It will also show
times when the portfolio was published, when the portfolio download links were
accessed, and when they expire.

User interface changes
======================

The admin interface will not be upgraded in the first phase of development. The design
and specification for visual changes is therefore deferred. Also, the upgrading of the
gallery and slideshow libraries to display portfolios is also deferred.

Permissions for portfolio creation
==================================

Any user in a group with "folio" permission can create portfolios. They can choose
whether the portfolio is private (visible only to them), visible to logged-in users,
or public. Separately they can also choose the same 3 options for who is allowed to
download a published zip of the whole portfolio. Only the owner or a folio
administrator can publish or change or delete the portfolio. The owner can add any
image to the portfolio that they already have permission to view.

A user in a group with "admin_folios" permission can see and manage any portfolio.
This will be required in future so that someone other than the portfolio creator has
the ability to manage portfolios globally.

Permissions for portfolio access
================================

When the current user is allowed to view a portfolio, viewing it from within the
QIS UI (admin interface, gallery or slideshow) will hide images that they do not have
permission to view. That is, the existing permissions engine will not be made
portfolio-aware and the existing permissions system will not be bypassed.

When the current user is allowed to download a portfolio as a zip, no additional
permissions checks will be made. That is, the system will not (in effect) open up
the zip file and re-check the view permission for everything inside it.

This latter directive does lead to an inconsistency whereby users may be allowed
to download an image that they cannot ordinarily view. This can be justified on
the basis that the main use-case for publishing a portfolio is to distribute it
easily by sending people the download URL. If this is not wanted, the portfolio
download permission can be restricted to either logged-in users or just the portfolio
owner.

Implementation schedule
=======================

Phase 1 (March 2018)

* Database changes
* Permissions engine changes
* File storage changes
* Full API support
* Download "original" type zip
* Download "image" with optional changes (batch operations) type zip

Phase 2 (TBD)

* Add portfolio downloads to system statistics
* "Shopping basket" and creation of portfolios from the UI
* Publishing/export as zip UI
* Administration UI
* Display portfolio in a public web page
* Display portfolio in gallery and slideshow viewers

URLs
====

Phase 1

* Provide a publicly accessible URL for downloading published zips
  * `/portfolios/<<portfolio human ID>>/downloads/<<zip filename>>.zip`
  * Invoke ensure_portfolio_permitted() for DOWNLOAD permission (see the
   'Permissions engine' section below)
  * Ensure that the response is sent using Flask's streaming API:  
   http://flask.pocoo.org/docs/0.12/patterns/streaming/

Phase 2

* Add URLs for users to create, publish, manage their own portfolios
  * `/portfolios/`
  * `/portfolios/<<portfolio human ID>>/`
  * `/portfolios/<<portfolio human ID>>/publish/`
  * `/portfolios/<<portfolio human ID>>/downloads/`
* Add URLs for administrators to view and manage all portfolios
  * `/admin/portfolios/`
  * `/admin/portfolios/<<portfolio ID>>/`
* Provide a portfolio viewing page
  * `/portfolios/<<portfolio human ID>>/`

Documentation
=============

Phase 1

* Update the project README (for back-end functionality)
* Update the API guide
* Update the changelog

Phase 2

* Update the project README (for front-end, screenshots)
* Update the user's guide (if we have one by then)
* Update the gallery viewer help page and demo
* Update the slideshow help page and demo
* Update the changelog

Database
========

Add new database tables as follows:

	folios
	---
	id
	human_id - manual reference (defaults to a UUID), visible in friendly URLs, unique
	name
	description
	owner_id - FK to users
	last_updated

	folioimages
	---
	id
	folio_id - FK to folios       } unique
	image_id - FK to images       } together
	parameters - json, optional
	filename - optional
	ordering_flag - default 0

	foliopermissions - same structure as folderpermissions
	---
	id
	folio_id - FK to folios                                   } unique
	group_id - FK to groups, system groups only in phase 1    } together
	access - 0 or 10 (VIEW) or 20 (DOWNLOAD) only in phase 1

	folioexports
	---
	id
	folio_id - FK to folios
	description
	originals - boolean
	parameters - json, optional (set when originals=False)
	task_id - FK to tasks, blank when zip creation finished
	filename - non-guessable filename, unique
	filesize
	created - timestamp
	keep_until - timestamp

	foliosaudit - same structure as imagesaudit
	---
	id
	folio_id - FK to folios
	user_id - FK to users, optional
	action - CREATED 1, EDITED 3, PUBLISHED 5, DOWNLOADED 6, PUBLISH_EXPIRED 7
	action_info
	action_time - timestamp

Permissions engine
==================

The permissions database and engine already has a user-level flag for whether
portfolios can be created, and a flag for whether to allow administration of
portfolios.

The engine will need new functions for calculating and caching whether a particular
user can view or download a particular portfolio. Suggested new methods:

* `is_portfolio_permitted(folio, folio_access, user=None)`
* `ensure_portfolio_permitted(folio, folio_access, user=None)`
* `calculate_portfolio_permissions(folio, user=None)`

Where folio access can be either VIEW, DOWNLOAD, CREATE, EDIT, or DELETE.
A blank user is a public (not logged in) user. The permissions rules are as follows:

* VIEW - Allow if the current user is a superuser, or has portfolio admin permission,
  or is the owner of the portfolio. Allow if the foliopermissions table has a entry
  with access level VIEW or above, for any of the current user's groups.
* DOWNLOAD - Allow if the current user is a superuser, or has portfolio admin permission,
  or is the owner of the portfolio. Allow if the foliopermissions table has a entry
  with access level DOWNLOAD or above, for any of the current user's groups.
* CREATE - Allow if the current user is a superuser, or has portfolio admin permission,
  or has the portfolio creation flag returned from calculate_system_permissions()
* EDIT, DELETE - Allow if the current user is a superuser, or has portfolio admin
  permission, or is the owner of the portfolio
* Otherwise deny

File storage
============

Published zip files will be stored inside the QIS images root folder, so that the
existing security checks (ensuring that file requests are restricted to the images
folder) also apply to zips.

QIS does not display files and folders beginning with ".", so we can add a hidden
folder into the standard images directory without it showing up in the admin
interface. The suggested new directory structure is:

* `<<images root>>/.folio_exports/<<Portfolio ID>>/<<zip filename>>.zip`

The code will need to create this folder structure (including parent folders) on demand.
A new housekeeping task will be required to delete expired zip files, and to delete any
empty folders that result.

REST API
========

TODO - get/add/change/delete collection headers
TODO - add/remove collection images
TODO - get/add/change/delete collection permissions
TODO - publish/unpublish collection
TODO - on deletes, cascade and remove exported zips

TODO reordering

TODO - some of these should work as GET calls without authentication - for portfolios marked as public

Future enhancements
===================

Provide a more seamless way of distributing portfolios - add a "send to recipient"
function that emails a portfolio download link to one or more email addresses.

* Requires an SMTP library and settings
* For added security, the download URL could require that the user enter their email
  address (to be cross-referenced with the list of addresses that the link was sent to)
* Consider download links that only work once (Mission Impossible mode)
* Provide a custom (more informative) 404 page for expired download links
