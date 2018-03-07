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
Unless set otherwise, the order of images in the portfolio will be the same order
that they were added in (earliest addition first).

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

## User interface changes

The admin interface will not be upgraded in the first phase of development. The design
and specification for visual changes is therefore deferred. Also, the upgrading of the
gallery and slideshow libraries to display portfolios is also deferred.

## Permissions for portfolio creation

Any user in a group with _folio_ permission can create portfolios. They can choose
whether the portfolio is private (visible only to them), visible to logged-in users,
or public. In addition they can also choose the same 3 levels for who is allowed to
download a published zip of the whole portfolio. Just as for image folders, download
permission will infer view permission. Only the owner or a folio administrator can
publish or change or delete the portfolio. The owner can add any image to the
portfolio that they already have permission to view.

A user in a group with _admin___folios_ permission can see and manage any portfolio.
This will be required in future so that someone other than the portfolio creator has
the ability to manage portfolios globally.

## Permissions for portfolio access

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

## Implementation schedule

Phase 1 (March 2018)

* Enable the _folio_ and _admin___folios_ flags (currently hidden) in the group
  permissions administration area
* Database changes
* Permissions engine changes
* File storage changes
* Full API support
* Download "original" type zip
* Download "image" with optional changes (batch operations) type zip
* Unit tests

Phase 2 (TBD)

* Add portfolio downloads to system statistics
* "Shopping basket" and creation of portfolios from the UI
* Publishing/export as zip UI
* Administration UI
* Display portfolio in a public web page
* Display portfolio in gallery and slideshow viewers

## URLs

Phase 1

* Provide a publicly accessible URL for downloading published zips
  * `/portfolios/<<portfolio human ID>>/downloads/<<zip filename>>.zip`
  * Invoke ensure_portfolio_permitted() for DOWNLOAD permission (see the
    'Permissions engine' section below)
  * Ensure that the response is sent using Flask's streaming API:  
    http://flask.pocoo.org/docs/0.12/patterns/streaming/
* Provide a basic portfolio viewing page
  * `/portfolios/<<portfolio human ID>>/`

Phase 2

* Add URLs for users to create, publish, manage their own portfolios
  * `/portfolios/`
  * `/portfolios/<<portfolio human ID>>/`
  * `/portfolios/<<portfolio human ID>>/publish/`
  * `/portfolios/<<portfolio human ID>>/downloads/`
* Add URLs for administrators to view and manage all portfolios
  * `/admin/portfolios/`
  * `/admin/portfolios/<<portfolio ID>>/`
* Enhance the portfolio viewing page
  * `/portfolios/<<portfolio human ID>>/`
  * Add options for viewing as a plain web page, lazy-loading web page,
    gallery and slideshow

## Documentation

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

## Database

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
	order_num - default 0

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
	action - CREATED 1, EDITED 3, PUBLISHED 5, DOWNLOADED 6, UNPUBLISHED 7
	action_info
	action_time - timestamp

## Permissions engine

The permissions database and engine already has a user-level flag for whether
portfolios can be created, and an administrator flag for whether to allow the
management of any portfolio.

The engine will need new functions for calculating and caching whether a particular
user can view or download a particular portfolio. Suggested new methods:

* `is_portfolio_permitted(folio, folio_access, user=None)`
* `ensure_portfolio_permitted(folio, folio_access, user=None)`
* `calculate_portfolio_permissions(folio, user=None)`

Where folio access can be either `VIEW, DOWNLOAD, CREATE, EDIT`, or `DELETE`.
A blank user is a public (not logged in) user, and (just as with folders) automatically
belongs to the built-in `Public` group. The permissions rules are as follows:

* `VIEW` - Allow if the current user is a superuser, or has portfolio admin permission,
  or is the owner of the portfolio. Allow if the foliopermissions table has an entry
  with access level `VIEW` or above, for any of the current user's groups.
* `DOWNLOAD` - Allow if the current user is a superuser, or has portfolio admin permission,
  or is the owner of the portfolio. Allow if the foliopermissions table has an entry
  with access level `DOWNLOAD` or above, for any of the current user's groups.
* `CREATE` - Allow if the current user is a superuser, or has portfolio admin permission,
  or has the portfolio creation flag returned from calculate_system_permissions()
* `EDIT, DELETE` - Allow if the current user is a superuser, or has portfolio admin
  permission, or is the owner of the portfolio. Unused now but for future compatibility:
  allow if the foliopermissions table has an entry with access level `EDIT, DELETE` or
  above, for any of the current user's groups.
* Otherwise deny

## File storage

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

## REST API

### Public portfolio access

These functions return binary data without a JSON wrapper, and provide "friendly"
URLs that can be accessed directly, shared via instant messages or email, or
embedded in web pages.

For publicly accessible portfolios, these services can be called from any anonymous
HTTP client. For restricted portfolios, either an API token or a QIS web session (via
the QIS login page) is required. The returned status codes are the standard values
as defined for the existing API.

* View portfolio
  * URL `/portfolios/[portfolio human ID]/`
  * `GET` method only
  * No parameters
  * Requires folio `VIEW` permission for the requested (human) ID
  * Returns HTML text
  * This is not actually a data API, but it is the companion of the public-facing
    portfolio download API and so documented here for completeness
  * To view the portfolio as JSON data, instead call `/api/v1/portfolios/[portfolio id]/`

* Download portfolio
  * URL `/portfolios/[portfolio human ID]/downloads/[zip filename].zip`
  * `GET` method only
  * No parameters
  * Requires folio `DOWNLOAD` permission for the requested (human) ID
  * Returns binary data (content type `application/zip`) as an attachment
  * Requires the portfolio to have already been published using the portfolio
    publish API
  * Adds a `foliosaudit` record with a `DOWNLOADED` action

### Public web services

For publicly accessible portfolios, these web services can be called from an anonymous
(not logged in) session without requiring an API authentication token. To see restricted
portfolios however, a token is required.

* List portfolios
  * URL `/api/v1/portfolios/`
  * `GET` method
  * No parameters
  * Returns a JSON list of portfolios for which the current user has folio `VIEW` permission
  * Returns portfolio header fields only (no image list and no audit trail)

* Portfolio details
  * URL `/api/v1/portfolios/[portfolio id]/`
  * `GET` method
  * No parameters
  * Requires folio `VIEW` permission for the requested ID
  * Returns a JSON object with full portfolio details, including the ordered image list,
    audit trail and list of published (and non-expired) zip files available for download

### Protected web services

These services require an authenticated web or API session and provide the ability
to create and manage portfolios.

Unlike the other "administration" level web services, portfolio functions will
be available to any user that has _folio_ permission enabled via one of their
groups. This is the rationale behind defining these URLs as `/api/v1/portfolios/`
rather than `/api/v1/admin/portfolios/`.

* Portfolio header management
  * URL `/api/v1/portfolios/` for `GET` (list) and `POST` (create)
  * URL `/api/v1/portfolios/[portfolio id]/` for `GET`, `PUT`, and `DELETE`
  * No parameters for `GET` or `DELETE`
  * Parameters `human_id` (optional), `name`, `description`, `internal_access`
    (0, 10, or 20), `public_access` (0, 10, or 20) for `POST` and `PUT`
  * No permissions required for `GET` (list)
    * But the returned list is filtered by `VIEW` permission
  * Folio `VIEW` permission required for `GET` (ID)
  * Folio `CREATE`, `EDIT` and `DELETE` permission required for `POST`, `PUT`,
    and `DELETE` methods respectively
  * Returns a list of portfolios, a single portfolio object, or nothing
    (after a delete)
  * Note that the 2 `GET` URLs actually implement the 2 "public web services"
    exactly as described above
  * The `human_id` parameter is a unique value that will be used to identify the
    portfolio in "friendly" shareable URLs. If no value is given, the application
    will generate a unique string value.
  * The `internal_access` and `public_access` values will act as shortcuts for which
    data rows should be present in the `foliopermissions` table. A future release
    of QIS may add new API functions, similar to those existing for
    _folder permissions_, that enable more granular permissions to be set for
    individual groups. If both values are zero, the portfolio will be private.
  * Deleting a portfolio will cascade the delete to the `folioimages`,
    `foliopermissions`, `folioexports` and `folioaudit` tables, and delete
    exported zip files from the filesystem
  * Adds a `foliosaudit` record for non-delete change actions

* Portfolio content / image list management
  * URL `/api/v1/portfolios/[portfolio id]/images/`
    for `GET` (list) and `POST` (add image)
  * URL `/api/v1/portfolios/[portfolio id]/images/[image id]/`
    for `GET`, `PUT` (change image) and `DELETE` (remove image)
  * URL `/api/v1/portfolios/[portfolio id]/images/[image id]/position/`
    for `PUT` (reorder images)
  * No parameters for `GET` and `DELETE`
  * Parameter `image_id` plus those below for `POST`
  * Parameters `filename` (optional), `index` (optional), `image_parameters`
    (optional JSON) for `PUT` (change image)
  * Parameter `index` for `PUT` (reorder)
  * Folio `VIEW` permission required for `GET`
  * Folio `EDIT` permission required otherwise
  * Returns a list of the portfolio-image objects in the portfolio, a single
    portfolio-image object, or nothing (after a delete)
  * The optional `filename` value overrides an image's default filename when the
    portfolio is published to a zip file
  * The optional `image_parameters` value will accept JSON in the same structure
    as defined for the existing _image templates_ API
  * Includes a calculated view URL field for each image, which will incorporate
    the `image_parameters` (if any)
  * Note that setting the `index` value using the _change image_ function will
    not change the ordering number on other images in the portfolio. This may
    result in duplicate values, with the order then being determined by which
    image was added to the portfolio first. To ensure that each image has a
    unique order number, use the _reorder image_ function.
  * Adds a `foliosaudit` record for change actions

* Portfolio publishing (export) and distribution
  * URL `/api/v1/portfolios/[portfolio id]/exports/`
    for `GET` (list) and `POST` (publish)
  * URL `/api/v1/portfolios/[portfolio id]/exports/[export id]/`
    for `GET` and `DELETE` (unpublish)
  * No parameters for `GET` and `DELETE`
  * Parameters `description` (optional), `originals`, `image_parameters` (optional
    JSON, ignored when `originals` is true), `expiry_time` for `POST`
  * Folio `VIEW` permission required for `GET`
  * Folio `EDIT` permission required otherwise
  * Returns a list of the portfolio-exports objects for the portfolio, a single
    portfolio-export object, or nothing (after a delete)
  * Includes a calculated download URL field in the returned object(s)
  * The optional `image_parameters` value will accept JSON in the same structure
    as defined for the existing _image templates_ API
  * When a new record is created, the returned `filename` and `filesize` fields
    will be blank, the status code will be `202`, and the `task_id` field will be
    set to a value that can be monitored with the _system tasks_ API
  * When the associated background task has completed, the `filename` and
    `filesize` fields will be set, and the `task_id` field blank
  * If the background task fails, the the `filename` and `filesize` fields will
    remain blank
  * It will not be possible to change a zip file (`PUT` is not supported)
  * Deleting an export will delete the associated zip file from the filesystem
  * Deleting an export before the associated task has completed will return an
    error
  * Adds a `foliosaudit` record for change actions

## Future enhancements

Provide a more seamless way of distributing portfolios - add a "send to recipient"
function that emails a portfolio download link to one or more email addresses.

* Requires an SMTP library and settings
* For added security, the download URL could require that the user enter their email
  address (to be cross-referenced with the list of addresses that the link was sent to)
* Consider download links that only work once (Mission Impossible mode)
* Provide a custom (more informative) 404 page for expired download links
