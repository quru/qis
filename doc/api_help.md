# API user's guide

Quru Image Server provides a web-based Application Programming Interface (API) so that
software developers can integrate QIS into their own web sites and imaging solutions.

The API consists a number of HTTP [RESTful web services](https://en.wikipedia.org/wiki/Representational_state_transfer#RESTful_web_services),
most of which return data in the [JSON](https://www.json.org/) format.

Features labelled with the ![Premium Edition](images/icon-premium-16.png) icon are only
available in the Premium Edition, they are ignored in the Basic Edition.

## Contents

* [About JSON](#json)
* [Using the API](#usage)
* [Public image services](#api_image_group)
    * [image - retrieve a processed image](#api_image)
    * [original - retrieve an unmodified image file](#api_original)
* [Public portfolio access](#api_folio_group)
    * [view - view a portfolio as a web page](#api_folio_view)
    * [download - download a portfolio as a zip file](#api_folio_download)
* [Public web services](#api_public)
    * [list - list the files in a folder path](#api_list)
    * [details - retrieve image information by path](#api_details)
    * [portfolio list - list available portfolios](#api_folio_list)
    * [portfolio details - retrieve portfolio information](#api_folio_details)
* [Protected web services](#api_private)
    * [token - obtain an API authentication token](#api_token)
    * [upload - upload an image](#api_upload)
    * [portfolios - manage portfolios](#api_folios)
    * [portfolio content - add and remove images in a portfolio](#api_folios_content)
    * [portfolio publishing - export a portfolio as a zip file](#api_folios_publish)
* [Administration web services](#api_admin)
    * [image data - manage image metadata](#api_data_images)
    * [image templates - manage image templates](#api_data_templates)
    * [users - manage user accounts](#api_data_users)
    * [groups - manage groups and system permissions](#api_data_groups)
    * [group membership - manage group members](#api_data_usergroups)
    * [folder permissions - manage access permissions](#api_data_permissions)
    * [disk files - manage the file system](#api_disk_files)
    * [disk folders - manage the file system](#api_disk_folders)
    * [system tasks - run background tasks](#api_tasks)

<a name="json"></a>
## About JSON

[JavaScript Object Notation](https://www.json.org/) (JSON) is a lightweight format used for
exchanging data. Despite being based on a small subset of JavaScript, JSON is language independent,
and is typically smaller and simpler to use than alternative data formats such as XML.

JSON handling libraries are available for almost all common programming languages in use today,
including Java, C, C#, PHP, Python, Ruby, Perl, Visual Basic, and so on.

Importantly for web applications, JSON data can be retrieved and converted directly into
JavaScript objects from within the web browser. Native support for the encoding and decoding of
JSON data is built into all modern web browsers, and can be emulated in older web browsers that
support JavaScript. In addition, most of the common JavaScript frameworks such as
[jQuery](https://jquery.com/) provide a simple means of calling JSON web services via XHR
(sometimes known as Ajax).

<a name="usage"></a>
## Using the API

### Calling an API function from a web page

The following JavaScript snippet illustrates how to call a public API function
from a web browser.

    // URL of the API function
    var url = 'https://images.example.com/api/v1/list/';
    
    // GET, POST, PUT, or DELETE (as supported by the API call)
    var method = 'GET';
    
    // Parameters for GET requests
    var params = '?path=myfolder';
    
    // Initiate a new request
    var request = new XMLHttpRequest();
    request.open(method, url + params, true);
    
    // Callback function on success
    request.onload = function() {
        alert('Successfully returned with status code ' + request.status);
        var resp = JSON.parse(request.responseText);
        alert('The folder contains ' + resp.data.length + ' images');
    };
    
    // Callback function on error
    request.onerror = function() {
    	alert('The request failed with status code ' + request.status);
    };
    
    request.send();

Or to send data to a protected web service:

    // URL of the API function
    var url = 'https://images.example.com/api/v1/admin/filesystem/folders/';
    
    // GET, POST, PUT, or DELETE (as supported by the API call)
    var method = 'POST';
    
    // Initiate a new request
    var request = new XMLHttpRequest();
    request.open(method, url, true);
    
    // Data for POST, PUT requests
    var data = 'path=/myfolder';
    request.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=utf-8');
    
    // Authentication token - call the "token" API function first to get this
    var token = 'abcdef0123456789abcdef0123456789';
    request.setRequestHeader("Authorization", "Basic " + btoa(token + ":blank"));
    
    // Callback function on success
    request.onload = function() {
        var resp = JSON.parse(request.responseText);
        alert('Folder created successfully with ID ' + resp.data.id);
    };
    
    // Callback function on error
    request.onerror = function() {
        alert('Folder creation failed with status code ' + request.status);
    };
    
    request.send(data);

### Calling an API function with curl

[curl](https://curl.haxx.se/) is a popular command line utility that allows you to make HTTP calls
without a web browser. It is available for all common operating systems, and allows you to create
useful scripts and quickly test individual functions.

This document will also use curl for most of its examples. In these, the `$` represents the
command line prompt, and is not to be typed. The curl equivalent of the above HTML example is simply:

	$ curl 'https://images.example.com/api/v1/list/?path=myfolder'

This displays the raw JSON text returned by the server, but does not check the values or process
them.

### Call methods

The following types of method are supported in general.
See the rest of the documentation for which methods are supported by which API calls.

<table class="padded">
	<tr class="odd"><td><i>Method</i></td><td><i>Meaning</i></td></tr>
	<tr class="even"><td><code>GET</code></td><td>Get and return an existing object</td></tr>
	<tr class="odd"><td><code>POST</code></td><td>Create and return a new object</td></tr>
	<tr class="even"><td><code>PUT</code></td><td>Update an existing object</td></tr>
	<tr class="odd"><td><code>DELETE</code></td><td>Delete an object</td></tr>
</table>

For the `PUT` and `POST` methods, parameters should be sent using standard HTML
form encoding (`application/x-www-form-urlencoded`). An exception to this is if
you are performing a file upload, in which case `multipart/form-data` encoding
is required.

Using form encoding for API parameters is unusual these days, with most modern
APIs preferring JSON inputs to match JSON outputs. Back in 2011 this choice was
made so that the image server API could be called directly from a standard HTML
form. A future release may add support for JSON-encoded parameters, but even in
back-end code it is trivial to form-encode data using a library such as `libcurl`
or [python-requests](http://docs.python-requests.org/en/master/user/quickstart/#more-complicated-post-requests).

### Return values

Every API call returns JSON text containing the requested data within a wrapper object.
The wrapper provides a status code and (if relevant) an error message.
The following JSON illustrates a successful API call:

	{
		status: 200,
		message: "OK",
		data: [1, 2, 3, 4, 5]
	}

The `data` attribute provides the return value from the API call, with the return value
being different for each API function. On error, the `data` attribute is usually set to `null`.

In the sample JavaScript code above, the line `var resp = JSON.parse(request.responseText);`
converts the returned JSON text into a JavaScript object, making it available as `resp`.
The code is then able to access the results of the function as `resp.status`, `resp.message`
and `resp.data`.

Because the API functions are called using HTTP, in addition to the status code returned
in the JSON there is also an HTTP status code associated with the whole response. At present
these status codes are set to the same value and you can check either one. In keeping with
HTTP standards, status codes beginning with 2xx indicate success, those beginning 4xx indicate
a problem with the client's request, and those beginning 5xx indicate a problem on the server side.

The following status codes may be returned:

<table class="padded">
	<tr class="odd"><td><i>Status</i></td><td><i>Meaning</i></td></tr>
	<tr class="even"><td>200</td><td>Success, complete</td></tr>
	<tr class="odd"><td>202</td><td>Success, but the function is continuing in the background</td></tr>
	<tr class="even"><td>400</td><td>A parameter to the function was missing or invalid</td></tr>
	<tr class="odd"><td>401</td><td>The client must be logged in to use the function</td></tr>
	<tr class="even"><td>403</td><td>The client does not have permission to perform the requested action</td></tr>
	<tr class="odd"><td>404</td><td>The requested path or image does not exist</td></tr>
	<tr class="odd"><td>405</td><td>The requested method (GET, POST, etc) is not supported</td></tr>
	<tr class="even"><td>409</td><td>The item already exists</td></tr>
	<tr class="odd"><td>415</td><td>The requested image is invalid or unsupported</td></tr>
	<tr class="even"><td>500</td><td>Some other error occurred (check the server log files)</td></tr>
	<tr class="odd"><td>503</td><td>The server is too busy (wait a short time and try again)</td></tr>
</table><br>


<a name="api_image_group"></a>
# Public image services

These services return binary image data without a JSON wrapper, and provide the
main way of accessing the images in the image library. They can be used directly
in HTML (with `img` or `picture` tags) or from JavaScript (with XHR or `fetch` requests),
or can form part of a back-end workflow using any language or library that supports
HTTP requests.

For publicly accessible images, these services can be called from any anonymous
HTTP client. For images with a [folder permission](#api_data_permissions) in place,
either an [API token](#api_token) or a QIS web session (via the QIS login page)
is required. The returned status codes are the same as those defined above for the
JSON web services.

<a name="api_image"></a>
## image
Creates and retrieves (as binary data) a processed image, based on the requested
template and imaging parameters. If no template is specified, the image will have
the system's default template applied to it. See the [imaging guide](image_help.md)
for the full documentation and list of available parameters.

### URL
* `/image`

### Supported methods
* `GET`

### Parameters
* `src` - Mandatory, text - Specifies the image path to retrieve
* _`[any]`_ - Optional, mixed - See the imaging guide for all other parameters

### Permissions required
* View permission for the folder containing the image
* If no authentication token has been provided,
  the image's folder must be publicly accessible

### Returns
Binary image data, with a content type that is determined by the image format
requested (or otherwise the default image format). On error, returns a non-200
status code and HTML text containing an error message.

### Example

Convert the file `myfile.jpg` to a `png` thumbnail and save it to disk:

    $ curl -o myfile.png 'https://images.example.com/image?src=myfolder/myfile.jpg&width=200&format=png'

<a name="api_original"></a>
## original
Retrieves an original, unmodified image file as binary data. See the
[imaging guide](image_help.md) for the full documentation and list of
available parameters.

### URL
* `/original`

### Supported methods
* `GET`

### Parameters
* `src` - Mandatory, text - Specifies the image path to retrieve
* _`[any]`_ - Optional, mixed - See the imaging guide for all other parameters

### Permissions required
* Download permission for the folder containing the image
* If no authentication token has been provided,
  the image's folder must have public download permission

### Returns
Binary image data, with a content type that is determined by the file's image format.
On error, returns a non-200 status code and HTML text containing an error message.

### Example

Download the original copy of `myfile.jpg` and save it to disk:

    $ curl -o myfile.jpg 'https://images.example.com/original?src=myfolder/myfile.jpg'


<a name="api_folio_group"></a>
# Public portfolio access

These services provide the main way of viewing or downloading an image portfolio,
returning a web page or a plain zip file without a JSON wrapper. For publicly
accessible portfolios, the URLs can be used directly in web pages, emails, instant
messages, or link sharing services.

For non-public portfolios, either an [API token](#api_token) or a QIS web session
(via the QIS login page) is required. The returned status codes are the same as
those defined above for the JSON web services.

<a name="api_folio_view"></a>
## view portfolio
Views a portfolio of images as a web page. To view the portfolio as JSON data,
instead use the [portfolio details](#api_folio_details) API function. If the
caller is not logged in, the portfolio must be publicly viewable.

### URL
* `/portfolios/[portfolio friendly id]/`

### Supported methods
* `GET`

### Parameters
* None

### Permissions required
* View permission for the portfolio

### Returns
A web page as HTML text. On error, returns a non-200 status code and HTML text
containing an error message.

### Example

	In a web browser, open:
	https://images.example.com/portfolios/the-spring-collection/

<a name="api_folio_download"></a>
## download portfolio
Downloads a portfolio as a zip file. The portfolio must already have been _published_
by its author in order to create the zip file; see the [portfolio publishing](#api_folios_publish)
API function for how to do this. If the caller is not logged in, the portfolio
must be publicly downloadable.

### URL
* `/portfolios/[portfolio friendly id]/downloads/[zip filename].zip`

### Supported methods
* `GET`

### Parameters
* None

### Permissions required
* Download permission for the portfolio

### Returns
A binary zip file, with content type `application/zip`.
On error, returns a non-200 status code and HTML text containing an error message.

### Example

    $ curl -o myfile.zip 'https://images.example.com/portfolios/the-spring-collection/downloads/a13d7382f1124b59b62618dd4df154ba.zip'


<a name="api_public"></a>
# Public web services

For publicly accessible images and portfolios, these web services can be called
from an anonymous (not logged in) session without requiring an [API authentication token](#api_token).
For images with a [folder permission](#api_data_permissions) in place or for
non-public portfolios, a token is required however.

<a name="api_list"></a>
## list
Retrieves the ordered list of the files within a folder path, returning the filename,
whether the file is a supported image type, and if so, a URL to display the image,
and optionally some additional image attributes. For unsupported file types, the
image URL and all other image attributes will be zero or empty.

To avoid performance issues, this function returns a maximum of 1,000 results.
To read the full set of results you can use the `start` and `limit` parameters
to implement paging. The end of the results list is reached when you get back
less than `limit` results.

### URL
* `/api/v1/list/`

### Supported methods
* `GET`

### Parameters
* `path` - Mandatory, text - Specifies the folder path to list
* `attributes` - Optional, boolean - When `true`, adds all the image fields from
  the image database to the returned objects. Set to `false` for improved performance
  if these fields are not required.
* `start` - Optional, integer - The zero-based result number to start from,
  default `0`.
* `limit` - Optional, integer - The maximum number of results to return,
  default `1000`, and maximum value `1000`.
* _`[any]`_ - Optional, mixed - Any additional parameters are appended to the
  returned image URLs so that for example the required image sizes can be specified.

### Permissions required
* View permission for the requested folder path
* If no authentication token has been provided, the folder must be publicly accessible

### Returns
An array of 0 or more objects in alphabetical order of filename.
If the array length equals `limit`, you can get the next page of results by making
a second call with the `start` parameter set.

### Examples

List the first 3 files in `myfolder`:

    $ curl 'https://images.example.com/api/v1/list/?path=myfolder&limit=3'
    {
      "data": [
        {
          "filename": "image1.jpg",
          "supported": true,
          "url": "https://images.example.com/image?src=myfolder/image1.jpg" 
          },
        {
          "filename": "image2.jpg",
          "supported": true,
          "url": "https://images.example.com/image?src=myfolder/image2.jpg"
        },
        {
          "filename": "image3.jpg",
          "supported": true,
          "url": "https://images.example.com/image?src=myfolder/image3.jpg"
        }
      ],
      "message": "OK",
      "status": 200
    }

List the next 2 files in `myfolder`:

    $ curl 'https://images.example.com/api/v1/list/?path=myfolder&start=3&limit=2'
    {
      "data": [
        {
          "filename": "image4.jpg",
          "supported": true,
          "url": "https://images.example.com/image?src=myfolder/image4.jpg"
          },
          {
            "filename": "misplaced.docx",
            "supported": false,
            "url": ""
          }
      ],
      "message": "OK",
      "status": 200
    }

List the files in `myfolder` with all image fields, and apply the _Thumbnail_
template inside the returned `url` for each image:

    $ curl 'https://images.example.com/api/v1/list/?path=myfolder&attributes=1&tmp=Thumbnail'
    {
      "data": [
        {
          "description": "",
          "download": true,
          "filename": "image1.jpg",
          "folder": {
            "id": 23,
            "name": "/myfolder",
            "parent_id": 1,
            "path": "/myfolder",
            "status": 1
          },
          "folder_id": 23,
          "height": 2448,
          "id": 114,
          "src": "myfolder/image1.jpg",
          "status": 1,
          "supported": true,
          "title": "",
          "url": "https://images.example.com/image?tmp=Thumbnail&src=myfolder/image1.jpg",
          "width": 3264
        },
        {
          "description": "",
          "download": true,
          "filename": "image2.jpg",
          "folder": {
            "id": 23,
            "name": "/myfolder",
            "parent_id": 1,
            "path": "/myfolder",
            "status": 1
          },
          "folder_id": 23,
          "height": 2171,
          "id": 116,
          "src": "myfolder/image2.jpg",
          "status": 1,
          "supported": true,
          "title": "",
          "url": "https://images.example.com/image?tmp=Thumbnail&src=myfolder/image2.jpg",
          "width": 3264
        },
        {
          "description": "",
          "download": true,
          "filename": "image3.jpg",
          "folder": {
            "id": 23,
            "name": "/myfolder",
            "parent_id": 1,
            "path": "/myfolder",
            "status": 1
          },
          "folder_id": 23,
          "height": 2448,
          "id": 119,
          "src": "myfolder/image3.jpg",
          "status": 1,
          "supported": true,
          "title": "",
          "url": "https://images.example.com/image?tmp=Thumbnail&src=myfolder/image3.jpg",
          "width": 3264
        }
      ],
      "message": "OK",
      "status": 200
    }

<a name="api_details"></a>
## details
Retrieves the attributes of a single image from its path.

### URL
* `/api/v1/details/`

### Supported methods
* `GET`

### Parameters
* `src` - Mandatory, text - The folder and filename of an image

### Permissions required
* View permission for the folder that the image resides in
* If no authentication token has been provided, the folder must be publicly accessible

### Returns
An object containing image attributes, as shown below.

### Example

    $ curl 'https://images.example.com/api/v1/details/?src=myfolder/image1.jpg'
    {
      "data": {
        "description": "",
        "download": true,
        "filename": "image1.jpg",
        "folder": {
          "id": 23,
          "name": "/myfolder",
          "parent_id": 1,
          "path": "/myfolder",
          "status": 1
        },
        "folder_id": 23,
        "height": 2448,
        "id": 114,
        "src": "myfolder/image1.jpg",
        "status": 1,
        "supported": true,
        "title": "",
        "url": "https://images.example.com/image?src=myfolder/image1.jpg",
        "width": 3264
      },
      "message": "OK",
      "status": 200
    }

<a name="api_folio_list"></a>
## portfolio list
Returns the list of portfolios that are allowed to be viewed by the caller.
Log in as a user with `admin_folios` permission enabled (in one of the user's
groups) to see the list of all portfolios. The returned portfolio objects do
not include image information but do include a URL for viewing the portfolio.

### URL
* `/api/v1/portfolios/`

### Supported methods
* `GET`

### Parameters
* None

### Permissions required
* None, but the results are filtered by portfolios that the caller can view

### Returns
An array of 0 or more objects ordered by portfolio name.

### Example

List all portfolios viewable by the current user:

	$ curl 'https://images.example.com/api/v1/portfolios/'
	{
	  "data": [
	    {
	      "description": "The admin user's favourite photos",
	      "downloads": [],
	      "human_id": "408eb84f7cb41a8b",
	      "id": 2,
	      "last_updated": "2018-03-09T16:54:51.662994Z",
	      "name": "Admin favourites",
	      "owner_id": 1,
	      "permissions": [
	        {
	          "access": 10,
	          "folio_id": 2,
	          "group_id": 1,
	          "id": 3
	        },
	        {
	          "access": 10,
	          "folio_id": 2,
	          "group_id": 2,
	          "id": 4
	        }
	      ],
	      "url": "https://images.example.com/portfolios/408eb84f7cb41a8b/"
	    },
	    {
	      "description": "The 2018 Spring Collection",
	      "downloads": [
	        {
	          "created": "2018-03-23T12:38:44.264952Z",
	          "description": "Originals export",
	          "filename": "a13d7382f1124b59b62618dd4df154ba.zip",
	          "filesize": 1330490,
	          "folio_id": 3,
	          "id": 2,
	          "keep_until": "2020-01-01T00:00:00Z",
	          "originals": true,
	          "parameters": {},
	          "task_id": null,
	          "url": "https://images.example.com/portfolios/the-spring-collection/downloads/a13d7382f1124b59b62618dd4df154ba.zip"
	        }
	      ],
	      "human_id": "the-spring-collection",
	      "id": 3,
	      "last_updated": "2018-03-09T16:39:05.342911Z",
	      "name": "Spring Collection 2018",
	      "owner_id": 2,
	      "permissions": [
	        {
	          "access": 10,
	          "folio_id": 3,
	          "group_id": 1,
	          "id": 1
	        },
	        {
	          "access": 10,
	          "folio_id": 3,
	          "group_id": 2,
	          "id": 2
	        }
	      ],
	      "url": "https://images.example.com/portfolios/the-spring-collection/"
	    }
	  ],
	  "message": "OK",
	  "status": 200
	}

<a name="api_folio_details"></a>
## portfolio details
Retrieves the full details of a portfolio, including its ordered image list,
audit trail and list of published (and non-expired) zip files available for download.

### URL
* `/api/v1/portfolios/`
* `/api/v1/portfolios/[portfolio id]/`

### Supported methods
* `GET`

### Parameters
* For `GET` without a numeric portfolio ID (first URL):
	* `human_id` - Mandatory, text - The unique "friendly" ID of the portfolio to retrieve
* None for `GET` with a numeric portfolio ID (second URL)

### Permissions required
* View permission for the requested portfolio ID

### Returns
The full portfolio as a JSON object.

### Examples

Retrieve portfolio with numeric ID `3`:

    $ curl 'https://images.example.com/api/v1/portfolios/3/'
    {
      "data": {
        "description": "The 2018 Spring Collection",
        "downloads": [
          {
            "created": "2018-03-23T12:38:44.264952Z",
            "description": "Originals export",
            "filename": "a13d7382f1124b59b62618dd4df154ba.zip",
            "filesize": 1330490,
            "folio_id": 3,
            "id": 2,
            "keep_until": "2020-01-01T00:00:00Z",
            "originals": true,
            "parameters": {},
            "task_id": null,
            "url": "https://images.example.com/portfolios/the-spring-collection/downloads/a13d7382f1124b59b62618dd4df154ba.zip"
          }
        ],
        "history": [
          {
            "action": 1,
            "action_info": "",
            "action_time": "2018-03-23T12:13:52.214960Z",
            "folio_id": 3,
            "id": 4,
            "user_id": 3
          },
          {
            "action": 3,
            "action_info": "products/p1-bags-a0001.jpg added",
            "action_time": "2018-03-23T12:24:27.452216Z",
            "folio_id": 3,
            "id": 5,
            "user_id": 3
          },
          {
            "action": 3,
            "action_info": "products/p1-bags-a0002.jpg added",
            "action_time": "2018-03-23T12:29:22.849761Z",
            "folio_id": 3,
            "id": 6,
            "user_id": 3
          },
          {
            "action": 3,
            "action_info": "products/p1-bags-a0003.jpg added",
            "action_time": "2018-03-23T12:29:30.137174Z",
            "folio_id": 3,
            "id": 7,
            "user_id": 3
          },
          {
            "action": 3,
            "action_info": "products/p1-bags-a0002.jpg moved to position 3",
            "action_time": "2018-03-23T12:32:50.556061Z",
            "folio_id": 3,
            "id": 8,
            "user_id": 3
          },
          {
            "action": 4,
            "action_info": "Originals export (expires Wed Jan  1 00:00:00 2020 UTC, images are unmodified originals)",
            "action_time": "2018-03-23T12:38:44.265397Z",
            "folio_id": 3,
            "id": 9,
            "user_id": 3
          }
        ],
        "human_id": "the-spring-collection",
        "id": 3,
        "images": [
          {
            "filename": "",
            "folio_id": 3,
            "id": 5,
            "image": {
              "description": "",
              "download": true,
              "filename": "p1-bags-a0001.jpg",
              "folder": {
                "id": 15,
                "name": "/products",
                "parent_id": 1,
                "path": "/products",
                "status": 1
              },
              "folder_id": 15,
              "height": 1754,
              "id": 85,
              "src": "products/p1-bags-a0001.jpg",
              "status": 1,
              "supported": true,
              "title": "",
              "url": "https://images.example.com/image?src=products/p1-bags-a0001.jpg",
              "width": 1239
            },
            "image_id": 85,
            "order_num": 0,
            "parameters": {},
            "url": "https://images.example.com/image?src=products/p1-bags-a0001.jpg"
          },
          {
            "filename": "",
            "folio_id": 3,
            "id": 7,
            "image": {
              "description": "",
              "download": true,
              "filename": "p1-bags-a0003.jpg",
              "folder": {
                "id": 15,
                "name": "/products",
                "parent_id": 1,
                "path": "/products",
                "status": 1
              },
              "folder_id": 15,
              "height": 1754,
              "id": 86,
              "src": "products/p1-bags-a0003.jpg",
              "status": 1,
              "supported": true,
              "title": "",
              "url": "https://images.example.com/image?src=products/p1-bags-a0003.jpg",
              "width": 1239
            },
            "image_id": 86,
            "order_num": 1,
            "parameters": {},
            "url": "https://images.example.com/image?src=products/p1-bags-a0003.jpg"
          },
          {
            "filename": "",
            "folio_id": 3,
            "id": 6,
            "image": {
              "description": "",
              "download": true,
              "filename": "p1-bags-a0002.jpg",
              "folder": {
                "id": 15,
                "name": "/products",
                "parent_id": 1,
                "path": "/products",
                "status": 1
              },
              "folder_id": 15,
              "height": 1754,
              "id": 84,
              "src": "products/p1-bags-a0002.jpg",
              "status": 1,
              "supported": true,
              "title": "",
              "url": "https://images.example.com/image?src=products/p1-bags-a0002.jpg",
              "width": 1239
            },
            "image_id": 84,
            "order_num": 2,
            "parameters": {},
            "url": "https://images.example.com/image?src=products/p1-bags-a0002.jpg"
          }
        ],
        "last_updated": "2018-03-23T12:29:30.137247Z",
        "name": "Spring Collection 2018",
        "owner_id": 3,
        "permissions": [
          {
            "access": 10,
            "folio_id": 3,
            "group_id": 2,
            "id": 6
          },
          {
            "access": 10,
            "folio_id": 3,
            "group_id": 1,
            "id": 5
          }
        ],
        "url": "https://images.example.com/portfolios/the-spring-collection/"
      },
      "message": "OK",
      "status": 200
    }

Or to retrieve the same portfolio by its human-readable "friendly" ID:

    $ curl 'https://images.example.com/api/v1/portfolios/?human_id=the-spring-collection'
    ...

<a name="api_private"></a>
# Protected web services

All other web services require the caller to be logged in so that permissions
can be checked and a username recorded in the audit trail. To log in using the
API, obtain an [API authentication token](#api_token) and then provide this along
with every function call.

<a name="api_token"></a>
## token
This service returns a unique time-limited token that can be used to call all the other API functions.
It is the equivalent of logging in on the QIS web site, and in fact requires the username and
password of a valid QIS user.

The advantage of obtaining a token is that the username and password are only required once,
and they never need to leave the server side. The token can then be passed through to a less secure
area (e.g. a web page) with the username and password never having been revealed. Note that the token
must also be treated securely, as anyone who takes a copy of it will then be able to use it to access
the API until that token expires. On a web site therefore, use an encrypted HTTPS connection and do
not pass around the token where it can be seen (e.g. on the end of a URL).

The token's expiry time is configured by the `API_TOKEN_EXPIRY_TIME` system setting.
The default value is 1 hour.

### URL
* `/api/v1/token/`

### Supported methods
* `POST`

### Parameters
* `username` - Mandatory, text - The username to authenticate with
* `password` - Mandatory, text - The password to authenticate with

These parameters can be supplied either as standard `POST` data,
or alternatively using [HTTP Basic Authentication](https://en.wikipedia.org/wiki/Basic_access_authentication) instead.

### Permissions required
* The username must match an existing QIS user account
* That user account must have the _Allow API_ setting enabled

### Returns
An object that currently has only one attribute - `token` - as a string.

To use the token, call the other API functions using
[HTTP Basic Authentication](https://en.wikipedia.org/wiki/Basic_access_authentication)
with the token as the username value. The password value is unused and can be blank or a dummy value.

### Example

	$ curl -X POST -u username:password 'https://images.example.com/api/v1/token/'
	{
	  "data": {
	    "token": "eyJhbGciOiJIUzI1NiIsImZ4cCI6MTQyOTcwNTI4NSwibWF0IjoxNDI5NzAxNjg1fQ.eyJ1c2VyX2lkIj5zfQ.nVdH2Eee8aw2lUamFSz3Wu6CKPl49GrrGz-2LgN791Y"
	  },
	  "message": "OK",
	  "status": 200
	}

<a name="api_upload"></a>
## upload
Uploads one or more image files, optionally replacing any existing files that already exist
in the same location.

### URL
* `/api/v1/upload/`

### Supported methods
* `POST`

### Parameters
* `files` - Mandatory, binary - One or more files to upload
* `path` - Optional, text - The destination folder path, when not using `path_index`.
  This folder path must already exist. If permitted, you can use the
  [disk folder](#api_disk_folders) API to find or create a folder path.
* `path_index` - Optional, integer - The destination folder path as an index (starting
  from 0) into the `IMAGE_UPLOAD_DIRS` list in the system settings. These pre-defined
  locations are considered to be trusted, and for all users the folder will be created
  if it does not already exist.
* `overwrite` - Mandatory, text/boolean - The action to take when a file already exists
  with the same name in the destination folder:
	* `yes` (or `true` or `1`) - Overwrite the existing file with the new one
	* `no` (or `false` or `0`) - Return a _file already exists_ error and do not overwrite it
	* `rename` - Rename the new file so that it can be saved, leaving the existing file unchanged

One of either `path` or `path_index` is required.

As is standard for file upload forms on the web, the parameter data must be
`multipart/form-data` encoded.

### Permissions required
* Upload permission for the destination folder

### Returns
An key/value object containing one entry for every uploaded file, where each key is the
original filename and each value is either success data or an error object. Success data
is in the same format returned by the [image details](#api_details) function. The error
object contains the same data as the standard API error response.

Note that for each uploaded file, the returned filename may be different from the original
filename. This happens when you upload with `overwrite=rename` and a file already exists,
when 2 files are uploaded with the same filename (e.g. coming from different directories),
or when the original filename contains dangerous or unsupported characters. By default,
unicode letters and numbers are allowed, but not unicode symbols. If you do not want to
allow unicode filenames at all, you can have them converted to their simplest form (that
is ASCII) by adding `ALLOW_UNICODE_FILENAMES = False` to your settings file.

If all files are uploaded successfully, the returned status will be `OK`.

If one file fails to upload, the function continues to try all the other files, but returns
a status of error (describing only the first error that occurred). The data object is returned
as described above, so you need to check the entry for each filename to determine which
files were uploaded and which failed (and why).

If there is an error with a parameter such that no uploads were even attempted, the
returned data object is `null`.

### Examples

Upload file `myimage.jpg` into the `test_images` folder, but not if it already exists:

    $ curl -X POST -u <token>:unused -F files=@myimage.jpg -F path=test_images -F overwrite=false 'https://images.example.com/api/v1/upload/'
    {
      "data": {
        "myimage.jpg": {
          "description": "",
          "download": true,
          "filename": "myimage.jpg",
          "folder": {
            "id": 2,
            "name": "/test_images",
            "parent_id": 1,
            "path": "/test_images",
            "status": 1
          },
          "folder_id": 2,
          "height": 1951,
          "id": 141,
          "src": "test_images/myimage.jpg",
          "status": 1,
          "supported": true,
          "title": "",
          "url": "https://images.example.com/image?src=test_images/myimage.jpg",
          "width": 3000
        }
      },
      "message": "OK",
      "status": 200
    }

Then running the same command a second time:

    $ curl -X POST -u <token>:unused -F files=@myimage.jpg -F path=test_images -F overwrite=false 'https://images.example.com/api/v1/upload/'
    {
      "data": {
        "myimage.jpg": {
          "error": {
            "data": null,
            "message": "The specified item already exists (file path 'test_images/myimage.jpg' already exists)",
            "status": 409
          }
        }
      },
      "message": "The specified item already exists (file path 'test_images/myimage.jpg' already exists)",
      "status": 409
    }

Running the same command a third time but with `overwrite=rename`:

    $ curl -X POST -u <token>:unused -F files=@myimage.jpg -F path=test_images -F overwrite=rename 'https://images.example.com/api/v1/upload/'
    {
      "data": {
        "myimage.jpg": {
          "description": "",
          "download": true,
          "filename": "myimage-001.jpg",
          "folder": {
            "id": 2,
            "name": "/test_images",
            "parent_id": 1,
            "path": "/test_images",
            "status": 1
          },
          "folder_id": 2,
          "height": 1951,
          "id": 142,
          "src": "test_images/myimage-001.jpg",
          "status": 1,
          "supported": true,
          "title": "",
          "url": "https://images.example.com/image?src=test_images/myimage-001.jpg",
          "width": 3000
        }
      },
      "message": "OK",
      "status": 200
    }

<a name="api_folios"></a>
## portfolios
Lists viewable portfolios, or gets, creates, updates, or deletes a single portfolio.

A portfolio is a collection of images that can be viewed together, downloaded
together, or transformed together (e.g. resized to the same dimensions, or have
a standard watermark applied). Unlike other objects, portfolios have a concept of
ownership. Any logged in user with the `folios` system permission can create a
portfolio and add images to it. They can choose whether the portfolio is visible
only to them, to other logged in users too, or is public. Separately they can
choose the same for who is allowed to download the portfolio as a zip file.
Only the portfolio owner or a user with the `admin_folios` system permission can
make changes to the portfolio or [publish it](#api_folios_publish) as a zip file.

### URL
* `/api/v1/portfolios/` for `GET` (list portfolios) and `POST` (create portfolio)
* `/api/v1/portfolios/` for `GET` (single portfolio by `human_id`)
* `/api/v1/portfolios/[portfolio id]/` for `GET`, `PUT`, and `DELETE`

### Supported methods
* `GET`
* `POST`
* `PUT`
* `DELETE`

### Parameters
* None for `GET` by numeric ID or for `DELETE`
* For `GET` by "friendly" ID:
	* `human_id` - Mandatory, text - The unique "friendly" ID to retrieve
* For `POST` and `PUT`:
	* `human_id` - Optional, text - A unique "friendly" ID that will be used to
	  identify the portfolio in the [view](#api_folio_view) and [download](#api_folio_download)
	  URLs. If not supplied or left blank a unique ID will be generated for you.
		Some characters are disallowed (see below).
	* `name` - Mandatory, text - A name for the portfolio
	* `description` - Mandatory, text - A description of the portfolio
	* `internal_access` - Mandatory, integer - The level of access to allow
	  for other logged in users:
		* `0` - No access (make the portfolio private)
		* `10` - View permission
		* `20` - View and download permission
	* `public_access` - Mandatory, integer - The level of access to allow
	  for public (not logged in) users:
		* `0` - No access (make the portfolio private)
		* `10` - View permission
		* `20` - View and download permission

Because it is used inside URLs, the `human_id` value is not allowed to contain
any of these characters: `% < > & . ? : /`.

### Permissions required
* None for `GET` (list portfolios),
  but the results are filtered by portfolios that the caller can view
* Portfolio view permission for `GET` (single portfolio)
* The `folios` system permission for `POST` (create portfolio)
* Portfolio ownership or the `admin_folios` system permission for `PUT` and `DELETE`

### Returns
A list of abbreviated portfolio objects (for the list URL), a single portfolio
object (for most other URLs), or nothing (after a delete).

If the `human_id` parameter is left blank when creating a portfolio, an automatically
generated ID will be present in the returned object. Each portfolio object includes
a URL for viewing the portfolio.

### Examples

To create a new portfolio:

	$ curl -X POST -u <token>:unused -F 'human_id=the-spring-collection' \
	       -F 'name=Spring Collection 2018' -F 'description=The 2018 Spring Collection' \
	       -F 'internal_access=10' -F 'public_access=10' \
	       'https://images.example.com/api/v1/portfolios/'
	{
	  "data": {
	    "description": "The 2018 Spring Collection",
	    "downloads": [],
	    "history": [
	      {
	        "action": 1,
	        "action_info": "",
	        "action_time": "2018-03-23T12:13:52.214960Z",
	        "folio_id": 3,
	        "id": 4,
	        "user_id": 3
	      }
	    ],
	    "human_id": "the-spring-collection",
	    "id": 3,
	    "images": [],
	    "last_updated": "2018-03-23T12:13:52.206066Z",
	    "name": "Spring Collection 2018",
	    "owner_id": 3,
	    "permissions": [
	      {
	        "access": 10,
	        "folio_id": 3,
	        "group_id": 1,
	        "id": 5
	      },
	      {
	        "access": 10,
	        "folio_id": 3,
	        "group_id": 2,
	        "id": 6
	      }
	    ],
	    "url": "https://images.example.com/portfolios/the-spring-collection/"
	  },
	  "message": "OK",
	  "status": 200
	}

To retrieve the portfolio by numeric ID:

    $ curl 'https://images.example.com/api/v1/portfolios/3/'
    ...

Or to retrieve the portfolio by its human-readable "friendly" ID:

    $ curl 'https://images.example.com/api/v1/portfolios/?human_id=the-spring-collection'
    ...

<a name="api_folios_content"></a>
## portfolio content
Adds and removes images to and from a portfolio, allows re-ordering of the image
list, and optionally sets portfolio-specific image changes.

The image changes apply only in the context of the portfolio, when the portfolio
is viewed or downloaded. The feature is intended to allow things like a custom
crop to be applied to a single image. If image changes are also requested at the
[publishing](#api_folios_publish) stage, the publishing changes are applied on
top of the single image changes.

### URL
* `/api/v1/portfolios/[portfolio id]/images/` for `GET` (list images) and `POST` (add image)
* `/api/v1/portfolios/[portfolio id]/images/[image id]/` for `GET`, `PUT`, and `DELETE`
* `/api/v1/portfolios/[portfolio id]/images/[image id]/position/` for `PUT` (reorder)

### Supported methods
* `GET`
* `POST`
* `PUT`
* `DELETE`

### Parameters
* None for `GET` or `DELETE`
* For reorder `PUT`:
	* `index` - Mandatory, integer - the new zero-based index to move the image to
* For add image `POST`:
	* `image_id` or `image_src` - Mandatory, integer or text - the unique ID or
	  path (folder and filename) of the image to add into the portfolio
* For add image and change image `POST` and `PUT`:
	* `filename` - Optional, text - Sets the filename to use for this image when
	  the portfolio is published to a zip file. Supports ASCII characters only due
	  to zip file limitations. Defaults to the image's original filename.
	* `index` - Optional, integer - Sets the zero-based numeric list index to insert
	  the image at. Defaults to 0. If all images are at position 0 they are ordered
	  by the time they were added (oldest first, newest last).
	* `image_parameters` - Optional, JSON text - A set of field/value-object pairs
	  that define portfolio-specific imaging operations for this image. The JSON
	  format is the same as when defining an [image template](#api_data_templates).

Note that setting the `index` parameter during a `POST` (add image) or
`PUT` (update image) operation will not change the ordering number on other
images in the portfolio. This may result in multiple images being at the same
position, with the order then being determined by which image was added to the
portfolio first. If this order is not what you want, or to ensure that each
image has a unique ordering number, use the explicit `/position/` reordering
function.

When using the reordering function, if the value of `index` is too high or too
low it will be adjusted, so you can simply pass a large number to implement a
_move to end_ function.

### Permissions required
* Portfolio view permission for `GET`
* Portfolio ownership or the `admin_folios` system permission for `POST`, `PUT`,
  and `DELETE`
* Folder view permission for the folder of the image being added for `POST`

### Returns
An ordered list of the images in the portfolio (for the list URL and the reorder
URL), a single portfolio-image object (for most other URLs), or nothing (after a
delete).

Each portfolio-image object includes a URL for requesting the image that
incorporates the operations given in the `image_parameters` parameter (if any).

### Examples

Add an image to a portfolio:

    $ curl -X POST -u <token>:unused -F 'image_id=85' 'https://images.example.com/api/v1/portfolios/3/images/'
    {
      "data": {
        "filename": "",
        "folio_id": 3,
        "id": 5,
        "image": {
          "description": "",
          "download": true,
          "filename": "p1-bags-a0001.jpg",
          "folder": {
            "id": 15,
            "name": "/products",
            "parent_id": 1,
            "path": "/products",
            "status": 1
          },
          "folder_id": 15,
          "height": 1754,
          "id": 85,
          "src": "products/p1-bags-a0001.jpg",
          "status": 1,
          "supported": true,
          "title": "",
          "url": "https://images.example.com/image?src=products/p1-bags-a0001.jpg",
          "width": 1239
        },
        "image_id": 85,
        "order_num": 0,
        "parameters": {},
        "url": "https://images.example.com/image?src=products/p1-bags-a0001.jpg"
      },
      "message": "OK",
      "status": 200
    }

Reorder the portfolio by moving image `84` to index `2` (third place because the
index number is 0-based):

    $ curl -X PUT -u <token>:unused -F 'index=2' 'https://images.example.com/api/v1/portfolios/3/images/84/position/'
    {
      "data": [
        {
          "filename": "",
          "folio_id": 3,
          "id": 5,
          "image": {
            "description": "",
            "download": true,
            "filename": "p1-bags-a0001.jpg",
            "folder": {
              "id": 15,
              "name": "/products",
              "parent_id": 1,
              "path": "/products",
              "status": 1
            },
            "folder_id": 15,
            "height": 1754,
            "id": 85,
            "src": "products/p1-bags-a0001.jpg",
            "status": 1,
            "supported": true,
            "title": "",
            "url": "https://images.example.com/image?src=products/p1-bags-a0001.jpg",
            "width": 1239
          },
          "image_id": 85,
          "order_num": 0,
          "parameters": {},
          "url": "https://images.example.com/image?src=products/p1-bags-a0001.jpg"
        },
        {
          "filename": "",
          "folio_id": 3,
          "id": 7,
          "image": {
            "description": "",
            "download": true,
            "filename": "p1-bags-a0003.jpg",
            "folder": {
              "id": 15,
              "name": "/products",
              "parent_id": 1,
              "path": "/products",
              "status": 1
            },
            "folder_id": 15,
            "height": 1754,
            "id": 86,
            "src": "products/p1-bags-a0003.jpg",
            "status": 1,
            "supported": true,
            "title": "",
            "url": "https://images.example.com/image?src=products/p1-bags-a0003.jpg",
            "width": 1239
          },
          "image_id": 86,
          "order_num": 1,
          "parameters": {},
          "url": "https://images.example.com/image?src=products/p1-bags-a0003.jpg"
        },
        {
          "filename": "",
          "folio_id": 3,
          "id": 6,
          "image": {
            "description": "",
            "download": true,
            "filename": "p1-bags-a0002.jpg",
            "folder": {
              "id": 15,
              "name": "/products",
              "parent_id": 1,
              "path": "/products",
              "status": 1
            },
            "folder_id": 15,
            "height": 1754,
            "id": 84,
            "src": "products/p1-bags-a0002.jpg",
            "status": 1,
            "supported": true,
            "title": "",
            "url": "https://images.example.com/image?src=products/p1-bags-a0002.jpg",
            "width": 1239
          },
          "image_id": 84,
          "order_num": 2,
          "parameters": {},
          "url": "https://images.example.com/image?src=products/p1-bags-a0002.jpg"
        }
      ],
      "message": "OK",
      "status": 200
    }

<a name="api_folios_publish"></a>
## portfolio publishing
Creates or deletes a downloadable export of a portfolio as a zip file. A
portfolio may be exported multiple times with different changes applied. For
example a zip of the unmodified original files, a zip of resized images all
saved as `jpg`, and a zip with all images having a colour profile applied.

When single image changes have been defined with the [content function](#api_folios_content),
the publishing changes (if any) will be applied on top. Note that when the
portfolio is exported as unmodified original files, both the publishing changes
and any single image changes are ignored.

Once created, a published zip file is not updated. So if images are added,
removed or changed in a portfolio, any existing zip files will become out of
date. If this is a concern, delete the existing exports and re-publish the
portfolio. Anyone attempting to download a deleted zip file will receive a
`404 not found` error.

Published zip files also have an expiry date, after which time they will be
automatically deleted. For zips that only need to be downloaded once you can
set for example a 7 day expiry date. Or to prevent expiry at all, set a 100 year
expiry date.

### URL
* `/api/v1/portfolios/[portfolio id]/exports/` for `GET` (list exports) and `POST`
* `/api/v1/portfolios/[portfolio id]/exports/[export id]/` for `GET` and `DELETE`

### Supported methods
* `GET`
* `POST`
* `DELETE`

### Parameters
* None for `GET` and `DELETE`
* For `POST`:
	* `description` - Mandatory, text - a description of the export
	  (can be left blank)
	* `originals` - Mandatory, boolean - whether to export the original unmodified
	  image files (when true, `image_parameters` will be ignored)
	* `expiry_time` - Mandatory, text - Date in the format `yyyy-mm-dd`, or a time
	  in the format `yyyy-mm-ddThh:mm:ss` for when the published zip file should
	  be automatically deleted. The time is specified in the UTC time zone and the
	  expiry routine runs hourly.
	* `image_parameters` - Optional, JSON text - A set of field/value-object pairs
	  that define any imaging operations required for this export. The JSON
	  format is the same as when defining an [image template](#api_data_templates).

### Permissions required
* Portfolio view permission for `GET`
* Portfolio ownership or the `admin_folios` system permission for `POST` and `DELETE`

### Returns
A list of published zip files for the portfolio (for the list URL), a single
portfolio-export object (for most other URLs), or nothing (after a delete).

Zip files are generated as a background task. When creating a new zip file with
the `POST` action, status `202` is returned, the `filename` and `filesize` fields
will be blank, and the `task_id` field will be set to a value that can be monitored
with the [system tasks API](#api_tasks). Once the task has completed, the `filename`
and `filesize` fields will be set, and the `task_id` field empty. If the task fails,
the error information can be queried via the system tasks API, where the task
object will contain an exception in the `result` field instead of the updated
portfolio-export object.

Each portfolio-export object includes a URL for downloading the zip file. This
will be empty at first until the background task to create the zip file has
completed.

Attempting to delete a zip file while the background creation task is still in
progress will result in a `503 server busy` error.

### Examples

Publish the portfolio's original unmodified image files:

	$ curl -X POST -u <token>:unused -F 'description=Originals export' \
	       -F 'originals=1' -F 'expiry_time=2020-01-01' 'https://images.example.com/api/v1/portfolios/3/exports/'
	{
	  "data": {
	    "created": "2018-03-23T12:38:44.264952Z",
	    "description": "Originals export",
	    "filename": "",
	    "filesize": 0,
	    "folio_id": 3,
	    "id": 2,
	    "keep_until": "2020-01-01T00:00:00Z",
	    "originals": true,
	    "parameters": {},
	    "task_id": 548,
	    "url": ""
	  },
	  "message": "OK task accepted",
	  "status": 202
	}

After the export task has completed, the filename and URL fields are set:

	$ curl -u <token>:unused 'https://images.example.com/api/v1/portfolios/3/exports/2/'
	{
	  "data": {
	    "created": "2018-03-23T12:38:44.264952Z",
	    "description": "Originals export",
	    "filename": "a13d7382f1124b59b62618dd4df154ba.zip",
	    "filesize": 1330490,
	    "folio_id": 3,
	    "id": 2,
	    "keep_until": "2020-01-01T00:00:00Z",
	    "originals": true,
	    "parameters": {},
	    "task_id": null,
	    "url": "https://images.example.com/portfolios/the-spring-collection/downloads/a13d7382f1124b59b62618dd4df154ba.zip"
	  },
	  "message": "OK",
	  "status": 200
	}

Publish the portfolio with all images resized to 500x500:

	$ curl -X POST -u <token>:unused -F 'description=500x500 thumbnails' \
	       -F 'originals=0' -F 'image_parameters={"width":{"value":500}, "height":{"value":500}}' \
	       -F 'expiry_time=2020-01-01' 'https://images.example.com/api/v1/portfolios/3/exports/'
	{
	  "data": {
	    "created": "2018-03-26T13:42:40.491120Z",
	    "description": "500 x 500 thumbnails",
	    "filename": "",
	    "filesize": 0,
	    "folio_id": 3,
	    "id": 3,
	    "keep_until": "2020-01-01T00:00:00Z",
	    "originals": false,
	    "parameters": {
	      "height": {
	        "value": 500
	      },
	      "width": {
	        "value": 500
	      }
	    },
	    "task_id": 590,
	    "url": ""
	  },
	  "message": "OK task accepted",
	  "status": 202
	}


<a name="api_admin"></a>
# Administration web services

These web services provide file system, user, group, data management, and system maintenance
facilities. All require an [API authentication token](#api_token) to be provided.

<a name="api_data_images"></a>
## image data
Gets or updates image metadata in the image database.

### URL
* `/api/v1/admin/images/[image id]/`

### Supported methods
* `GET`
* `PUT`

### Parameters
* None for `GET`
* For `PUT`:
	* `title` - Mandatory, text - the image title
	* `description` - Mandatory, text - the image description

### Permissions required
* View permission for the folder that the image resides in
* Edit permission is required for `PUT`

### Returns
The image's database object.
The image `status` field has value `1` for active, or `0` for deleted.

### Examples

Retrieve image details by image ID:

    $ curl -u <token>:unused 'https://images.example.com/api/v1/admin/images/141/'
    {
      "data": {
        "description": "",
        "download": true,
        "filename": "myimage.jpg",
        "folder": {
          "id": 2,
          "name": "/test_images",
          "parent_id": 1,
          "path": "/test_images",
          "status": 1
        },
        "folder_id": 2,
        "height": 1951,
        "id": 141,
        "src": "test_images/myimage.jpg",
        "status": 1,
        "supported": true,
        "title": "",
        "url": "https://images.example.com/image?src=test_images/myimage.jpg",
        "width": 3000
      },
      "message": "OK",
      "status": 200
    }

Update the title and description of the image:

    $ curl -X PUT -u <token>:unused -F 'title=my sample image' -F 'description=the updated description of my sample image' 'https://images.example.com/api/v1/admin/images/141/'
    {
      "data": {
        "description": "the updated description of my sample image",
        "download": true,
        "filename": "myimage.jpg",
        "folder": {
          "id": 2,
          "name": "/test_images",
          "parent_id": 1,
          "path": "/test_images",
          "status": 1
        },
        "folder_id": 2,
        "height": 1951,
        "id": 141,
        "src": "test_images/myimage.jpg",
        "status": 1,
        "supported": true,
        "title": "my sample image",
        "url": "https://images.example.com/image?src=test_images/myimage.jpg",
        "width": 3000
      },
      "message": "OK",
      "status": 200
    }

<a name="api_data_templates"></a>
## image templates
Lists all image templates, or gets, creates, updates, or deletes a single template.

A template combines a number of imaging operations into a named group, or a preset,
as described in the [imaging guide](image_help.md#option_tmp).

### URL
* `/api/v1/admin/templates/` for `GET` (list templates) and `POST`
* `/api/v1/admin/templates/[template id]/` for `GET`, `PUT`, and `DELETE`

### Supported methods
* `GET`
* `POST`
* `PUT`
* `DELETE`

### Parameters
* None for `GET` or `DELETE`
* For `POST` and `PUT`:
	* `name` - Mandatory, text - A unique name for the template
	* `description` - Mandatory, text - A description for the template
	* `template` - Mandatory, JSON text - A set of parameter-name/value-object
	    pairs that define the imaging operations to apply. See the examples below
			for the list of possible parameter names. Operations to be skipped can 
			either have their values set to `null` or simply be omitted from the JSON.

![Premium Edition](images/icon-premium-16.png) The template JSON can contain any
parameter name that is valid in the Premium Edition. When used in the Basic Edition,
any unsupported parameters are simply ignored by the imaging engine.

### Permissions required
* None for `GET`
* Super user for `POST`, `PUT`, `DELETE`

### Returns
A list of template objects (for the list URL), a single template object
(for most other URLs), or nothing (after a delete).

In the template object, the `template` field contains image generation
parameter names and values. Note that some parameters are named differently
here than in the `image` [web interface](image_help.md).

Values are either `null` or excluded from the output if the template does not set
them. Existing older templates may also be missing fields that have been added in
more recent versions of the software.

### Examples

	$ curl -u <token>:unused 'https://images.example.com/api/v1/admin/templates/1/'
	{
	  "data": {
	    "description": "Defines a 200x200 JPG image that would be suitable for use as a thumbnail image on a web site.",
	    "id": 1,
	    "name": "SmallJpeg",
	    "template": {
	      "align_h": { "value": "C0.5" },
	      "align_v": { "value": "C0.5" },
	      "attachment": { "value": false },
	      "bottom": { "value": null },
	      "colorspace": { "value": "rgb" },
	      "crop_fit": { "value": false },
	      "dpi_x": { "value": null },
	      "dpi_y": { "value": null },
	      "expiry_secs": { "value": 604800 },
	      "fill": { "value": "#ffffff" },
	      "flip": { "value": "" },
	      "format": { "value": "jpg" },
	      "height": { "value": 200 },
	      "icc_bpc": { "value": false },
	      "icc_intent": { "value": "" },
	      "icc_profile": { "value": "" },
	      "left": { "value": null },
	      "overlay_opacity": { "value": null },
	      "overlay_pos": { "value": "" },
	      "overlay_size": { "value": null },
	      "overlay_src": { "value": "" },
	      "page": { "value": null },
	      "quality": { "value": 80 },
	      "record_stats": { "value": true },
	      "right": { "value": null },
	      "rotation": { "value": null },
	      "sharpen": { "value": null },
	      "size_fit": { "value": false },
	      "strip": { "value": true },
	      "tile": { "value": null },
	      "top": { "value": null },
	      "width": { "value": 200 }
	    }
	  },
	  "message": "OK",
	  "status": 200
	}

Create a new template `grey-thumb` that creates 400x400 square greyscale images:

	$ curl -X POST -u <token>:unused -F 'name=grey-thumb' \
	       -F 'description=Defines a greyscale thumbnail with a black fill' \
	       -F 'template={ "colorspace":{"value":"gray"}, "width":{"value":400}, "height":{"value":400}, "fill":{"value":"black"} }' \
	       'https://images.example.com/api/v1/admin/templates/'
	{
	  "data": {
	    "description": "Defines a greyscale thumbnail with a black fill",
	    "id": 3,
	    "name": "grey-thumb",
	    "template": {
	      "colorspace": { "value": "gray" },
	      "fill": { "value": "black" },
	      "height": { "value": 400 },
	      "width": { "value": 400 }
	    }
	  },
	  "message": "OK",
	  "status": 200
	}

Delete the template that was just created:

	$ curl -X DELETE -u <token>:unused 'https://images.example.com/api/v1/admin/templates/3/'
	{
	  "data": null,
	  "message": "OK",
	  "status": 200
	}

<a name="api_data_users"></a>
## users
Lists all user accounts, or gets, creates, updates, or deletes a single user account.

### URL
* `/api/v1/admin/users/` for `GET` (list users) and `POST`
* `/api/v1/admin/users/[user id]/` for `GET`, `PUT`, and `DELETE`

### Supported methods
* `GET`
* `POST`
* `PUT`
* `DELETE`

### Parameters
* None for `GET` or `DELETE`
* For `POST` and `PUT`:
	* `first_name` - Mandatory, text - The user's first name
	* `last_name` - Mandatory, text - The user's last name
	* `email` - Mandatory, text - The user's email address
	* `username` - Mandatory, text - A unique username for the account
	* `password` - Mandatory for `POST`, optional for `PUT`, text - The account password
	* `auth_type` - Mandatory, integer - Should be set to `1`
	* `allow_api` - Mandatory, boolean - Whether this account should be allowed to request
	  an API authentication token

### Permissions required
* The current user can `GET` and `PUT` their own user account
* But otherwise user administration permission is required

### Returns
A list of user objects (for the list users URL), or a single user object (for all other URLs).
The user `status` field has value `1` for active, or `0` for deleted.

### Examples

List all users:

	$ curl -u <token>:unused 'https://images.example.com/api/v1/admin/users/'
	{
	  "data": [
	    {
	      "allow_api": false,
	      "auth_type": 1,
	      "email": "",
	      "first_name": "Administrator",
	      "id": 1,
	      "last_name": "",
	      "status": 1,
	      "username": "admin"
	    },
	    {
	      "allow_api": true,
	      "auth_type": 1,
	      "email": "",
	      "first_name": "Matt",
	      "id": 2,
	      "last_name": "Fozard",
	      "status": 1,
	      "username": "matt"
	    }
	  ],
	  "message": "OK",
	  "status": 200
	}

Retrieve a single user:

	$ curl -u <token>:unused 'https://images.example.com/api/v1/admin/users/2/'
	{
	  "data": {
	    "allow_api": true,
	    "auth_type": 1,
	    "email": "",
	    "first_name": "Matt",
	    "id": 2,
	    "last_name": "Fozard",
	    "status": 1,
	    "username": "matt"
	  },
	  "message": "OK",
	  "status": 200
	}

Update user details:

	$ curl -X PUT -u <token>:unused -F 'first_name=Matthew' -F 'last_name=Fozard' -F 'username=mattfoo' -F 'email=matt@quru.com' -F 'auth_type=1' -F 'allow_api=true' 'https://images.example.com/api/v1/admin/users/2/'
	{
	  "data": {
	    "allow_api": true,
	    "auth_type": 1,
	    "email": "matt@quru.com",
	    "first_name": "Matthew",
	    "id": 2,
	    "last_name": "Fozard",
	    "status": 1,
	    "username": "mattfoo"
	  },
	  "message": "OK",
	  "status": 200
	}

<a name="api_data_groups"></a>
## groups
Lists all user groups, or gets, creates, updates, or deletes a single group.
Groups are used to define the system-wide access permissions for logged in users.
The special system group _Public_ defines access permissions for anonymous (not logged in) users.
You can use the [folder permissions](#api_data_permissions) API to define folder-level access
controls.

### URL
* `/api/v1/admin/groups/` for `GET` (list groups) and `POST`
* `/api/v1/admin/groups/[group id]/` for `GET`, `PUT`, and `DELETE`

### Supported methods
* `GET`
* `POST`
* `PUT`
* `DELETE`

### Parameters
* None for `GET` or `DELETE`
* For `POST` and `PUT`:
	* `name` - Mandatory, text - the unique name of the group
	* `description` - Mandatory, text - a description of the group
	* `group_type` - Mandatory, integer - set to `1` for required system groups that must not
	  be deleted, set to `2` for normal, user-defined groups
	* `access_folios` - Mandatory, boolean - Whether the group allows the creation of portfolios
	* `access_reports` - Mandatory, boolean - Whether the group provides access to reports
	* `access_admin_users` - Mandatory, boolean - Whether the group provides user administration
	  permission (and basic group administration)
	* `access_admin_files` - Mandatory, boolean - Whether the group provides file administration
	  permission (change or delete any file or folder, regardless of folder permissions)
	* `access_admin_folios` - Mandatory, boolean - Whether the group provides portfolio
	  administration permission (create, change and delete any user's portfolios)
	* `access_admin_permissions` - Mandatory, boolean - Whether the group provides permissions
	  administration (and full group administration)
	* `access_admin_all` - Mandatory, boolean - Whether the group provides _super user_
	  permission (full access to everything)

### Permissions required
* User administration permission is required for `GET`, or to `PUT` an updated group name or
  description
* Permissions administration permission is additionally required for `POST` or `DELETE`, or
  to `PUT` updated permissions flags for a group

### Returns
A list of group objects (for the list groups URL), a single group object (for most other URLs),
or nothing (after a delete).

### Examples

List all groups:

	$ curl -u <token>:unused 'https://images.example.com/api/v1/admin/groups/'
	{
	  "data": [
	    {
	      "description": "Provides full administration access",
	      "group_type": 1,
	      "id": 3,
	      "name": "Administrators",
	      "permissions": {
	        "admin_all": true,
	        "admin_files": true,
	        "admin_folios": true,
	        "admin_permissions": true,
	        "admin_users": true,
	        "folios": true,
	        "group_id": 3,
	        "reports": true
	      }
	    },
	    {
	      "description": "Provides the default access rights for known users",
	      "group_type": 1,
	      "id": 2,
	      "name": "Normal users",
	      "permissions": {
	        "admin_all": false,
	        "admin_files": false,
	        "admin_folios": false,
	        "admin_permissions": false,
	        "admin_users": false,
	        "folios": false,
	        "group_id": 2,
	        "reports": false
	      }
	    },
	    {
	      "description": "Provides the access rights for unknown users",
	      "group_type": 1,
	      "id": 1,
	      "name": "Public",
	      "permissions": {
	        "admin_all": false,
	        "admin_files": false,
	        "admin_folios": false,
	        "admin_permissions": false,
	        "admin_users": false,
	        "folios": false,
	        "group_id": 1,
	        "reports": false
	      }
	    }
	  ],
	  "message": "OK",
	  "status": 200
	}

Create a new _Website editors_ group that grants access to reports and permission
to change or delete all files and folders:

	$ curl -X POST -u <token>:unused -F 'name=Website editors' -F 'description=Access to reports and to change any file or folder' -F 'group_type=2' -F 'access_folios=false' -F 'access_reports=true' -F 'access_admin_users=false' -F 'access_admin_files=true' -F 'access_admin_folios=false' -F 'access_admin_permissions=false' -F 'access_admin_all=false' 'https://images.example.com/api/v1/admin/groups/'
	{
	  "data": {
	    "description": "Access to reports and to change any file or folder",
	    "group_type": 2,
	    "id": 7,
	    "name": "Website editors",
	    "permissions": {
	      "admin_all": false,
	      "admin_files": true,
	      "admin_folios": false,
	      "admin_permissions": false,
	      "admin_users": false,
	      "folios": false,
	      "group_id": 7,
	      "reports": true
	    },
	    "users": []
	  },
	  "message": "OK",
	  "status": 200
	}

Delete the group that was just created:

	$ curl -X DELETE -u <token>:unused 'https://images.example.com/api/v1/admin/groups/7/'
	{
	  "data": null,
	  "message": "OK",
	  "status": 200
	}

<a name="api_data_usergroups"></a>
## group membership
Adds a user to a group or removes a user from a group. 
Use the [groups](#api_data_groups) API to list the members of a group.

### URL
* `/api/v1/admin/groups/[group id]/members/` for `POST`
* `/api/v1/admin/groups/[group id]/members/[user id]/` for `DELETE`

### Supported methods
* `POST`
* `DELETE`

### Parameters
* None for `DELETE`
* For `POST`:
	* `user_id` - Mandatory, integer - The ID of the user to add to the group

### Permissions required
* User administration permission is required as a minimum
* Permissions administration permission is additionally required to add a user to a group
  that itself grants permissions administration or _super user_

### Returns
No return value.

### Examples

List the members of the _Web editors_ group ID `4`:

	$ curl -u <token>:unused 'https://images.example.com/api/v1/admin/groups/4/'
	{
	  "data": {
	    "description": "Those that are editing the web pages and managing the /web directory of this instance",
	    "group_type": 2,
	    "id": 4,
	    "name": "Web editors",
	    "permissions": {
	      "admin_all": false,
	      "admin_files": false,
	      "admin_folios": false,
	      "admin_permissions": false,
	      "admin_users": false,
	      "folios": true,
	      "group_id": 4,
	      "reports": true
	    },
	    "users": [
	      {
	        "allow_api": false,
	        "auth_type": 1,
	        "email": "jc@quru.com",
	        "first_name": "JC",
	        "id": 3,
	        "last_name": "",
	        "status": 1,
	        "username": "jc"
	      },
	      {
	        "allow_api": false,
	        "auth_type": 1,
	        "email": "",
	        "first_name": "Jenny",
	        "id": 2,
	        "last_name": "Darcs",
	        "status": 1,
	        "username": "jenny"
	      }
	    ]
	  },
	  "message": "OK",
	  "status": 200
	}

Remove one of the members from the group:

	$ curl -X DELETE -u <token>:unused 'https://images.example.com/api/v1/admin/groups/4/members/2/'
	{
	  "data": null,
	  "message": "OK",
	  "status": 200
	}

Get the group again, showing the updated member list:

	$ curl -u <token>:unused 'https://images.example.com/api/v1/admin/groups/4/'
	{
	  "data": {
	    "description": "Those that are editing the web pages and managing the /web directory of this instance",
	    "group_type": 2,
	    "id": 4,
	    "name": "Web editors",
	    "permissions": {
	      "admin_all": false,
	      "admin_files": false,
	      "admin_folios": false,
	      "admin_permissions": false,
	      "admin_users": false,
	      "folios": true,
	      "group_id": 4,
	      "reports": true
	    },
	    "users": [
	      {
	        "allow_api": false,
	        "auth_type": 1,
	        "email": "jc@quru.com",
	        "first_name": "JC",
	        "id": 3,
	        "last_name": "",
	        "status": 1,
	        "username": "jc"
	      }
	    ]
	  },
	  "message": "OK",
	  "status": 200
	}

<a name="api_data_permissions"></a>
## folder permissions
Lists all defined folder permissions, or gets, creates, updates, or deletes a single
permission for a particular folder and group.

Folder permissions are hierarchical, meaning that if you set a permission for `/myfolder`, that
rule will be inherited by `/myfolder/subfolder1`, `/myfolder/subfolder2`, and so on. Similarly,
the permission you define for the root folder `/` acts as the default permission for all other
folders.

The permission record for the root folder `/` and the _Public_ group determines whether your
images default to being publicly visible or not.

If a group has _file administration_ permission enabled, this overrides the normal
folder permissions and grants members of the group full access to all folders.

### URL
* `/api/v1/admin/permissions/` for `GET` (list permissions) and `POST`
* `/api/v1/admin/permissions/[permission id]/` for `GET`, `PUT`, and `DELETE`

### Supported methods
* `GET`
* `POST`
* `PUT`
* `DELETE`

### Parameters
* None for `GET` or `DELETE`
* For `POST` and `PUT`:
	* `group_id` - Mandatory, integer - the ID of the group to set a folder permission for
	* `folder_id` - Mandatory, integer - the ID of the folder to set a permission for
	* `access` - Mandatory, integer - the permission level to set:
		* `0` - No access
		* `10` - View images
		* `20` - View and download images
		* `30` - Edit image metadata (plus the above)
		* `40` - Upload files to the folder (plus the above)
		* `50` - Delete files from the folder (plus the above)
		* `60` - Create new sub-folders (plus the above)
		* `70` - Delete the entire folder (plus the above)

Note that `group_id` and `folder_id` are not changed during a `PUT` operation.

### Permissions required
* Permissions administration

### Returns
A list of folder permission objects (for the list URL), a single folder permission object
(for most other URLs), or nothing (after a delete).

### Examples

List all defined folder permissions:

	$ curl -u <token>:unused 'https://images.example.com/api/v1/admin/permissions/'
	{
	  "data": [
	    {
	      "access": 70,
	      "folder_id": 1,
	      "group_id": 3,
	      "id": 3
	    },
	    {
	      "access": 20,
	      "folder_id": 1,
	      "group_id": 1,
	      "id": 1
	    },
	    {
	      "access": 20,
	      "folder_id": 1,
	      "group_id": 2,
	      "id": 2
	    }
	  ],
	  "message": "OK",
	  "status": 200
	}

Allow any logged in user to upload images by default:

	$ curl -X PUT -u <token>:unused -F 'group_id=2' -F 'folder_id=1' -F 'access=40' 'https://images.example.com/api/v1/admin/permissions/2/'
	{
	  "data": {
	    "access": 40,
	    "folder_id": 1,
	    "group_id": 2,
	    "id": 2
	  },
	  "message": "OK",
	  "status": 200
	}

<a name="api_disk_files"></a>
## disk files
Moves, renames, or deletes an image file on disk, and updates the associated metadata and
audit trail. Use the [upload](#api_upload) API to create a new file.

### URL
* `/api/v1/admin/filesystem/images/[image id]/`

### Supported methods
* `PUT`
* `DELETE`

### Parameters
* None for `DELETE`
* For `PUT`:
	* `path` - Mandatory, text - the new path and filename for the image file. If the folder
	  path changes, the file will be moved. If only the filename changes, the file will be
	  renamed.

### Permissions required
* Either file administration permission or
* For `PUT` when renaming, upload permission for the folder that contains the image
* For `PUT` when moving, delete permission for the folder that currently contains the
  image, and upload permission for the destination folder
* For `DELETE`, delete file permission for the folder that contains the image

### Returns
The image's updated database object.

### Examples

To move image ID `141` _myimage.jpg_ to the `web` folder:

    $ curl -X PUT -u <token>:unused -F 'path=/web/myimage.jpg' 'https://images.example.com/api/v1/admin/filesystem/images/141/'
    {
      "data": {
        "description": "the updated description of my sample image",
        "download": true,
        "filename": "myimage.jpg",
        "folder": {
          "id": 24,
          "name": "/web",
          "parent_id": 1,
          "path": "/web",
          "status": 1
        },
        "folder_id": 24,
        "height": 1951,
        "id": 141,
        "src": "web/myimage.jpg",
        "status": 1,
        "supported": true,
        "title": "my sample image",
        "url": "https://images.example.com/image?src=web/myimage.jpg",
        "width": 3000
      },
      "message": "OK",
      "status": 200
    }

Then to delete the file:

    $ curl -X DELETE -u <token>:unused 'https://images.example.com/api/v1/admin/filesystem/images/141/'
    {
      "data": {
        "description": "the updated description of my sample image",
        "download": true,
        "filename": "myimage.jpg",
        "folder": {
          "id": 24,
          "name": "/web",
          "parent_id": 1,
          "path": "/web",
          "status": 1
        },
        "folder_id": 24,
        "height": 1951,
        "id": 141,
        "src": "web/myimage.jpg",
        "status": 0,
        "supported": true,
        "title": "my sample image",
        "url": "https://images.example.com/image?src=web/myimage.jpg",
        "width": 3000
      },
      "message": "OK",
      "status": 200
    }

<a name="api_disk_folders"></a>
## disk folders
Finds a folder by path or database ID.
Or creates, moves, renames, or deletes a disk folder, and updates the associated metadata.

Moving, renaming or deleting a folder is a recursive operation that also affects all the
sub-folders and files it contains, and can therefore take a long time. In the same way note
that if you rename a folder, this changes the paths of all the images contained within.

### URL
* `/api/v1/admin/filesystem/folders/` for `GET` (by path) and `POST`
* `/api/v1/admin/filesystem/folders/[folder id]/` for `GET`, `PUT` and `DELETE`

### Supported methods
* `GET`
* `POST`
* `PUT`
* `DELETE`

### Parameters
* None for `GET` and `DELETE` (by ID)
* For `GET` (by path):
	* `path` - Mandatory, text - the path of a disk folder to retrieve.
* For `POST` and `PUT`:
	* `path` - Mandatory, text - the new path for the disk folder. If the parent part of the
	  folder path changes, the folder will be moved. If only the folder's own name changes,
	  the folder will be renamed.

### Permissions required
* Either file administration permission or
* For `GET`, view permission for the requested folder
* For `POST`, create sub-folder permission for the nearest existing parent folder
* For `PUT` when renaming, create sub-folder permission for the parent folder
* For `PUT` when moving, full delete permission for the current parent folder,
  and create sub-folder permission for the destination parent folder
* For `DELETE`, full delete permission for the parent folder

### Returns
For `GET`, returns the folder's database object including one level of sub-folders
in the `children` attribute. The folder `status` field has value `1` for active,
or `0` for deleted.

For `POST`, returns the new folder's database object.

For `PUT` and `DELETE`, if the function completes in less than 30 seconds,
returns the folder's updated database object. If however the function is still
ongoing after 30 seconds, returns status `202` and a task object that you can
track using the [system tasks](#api_tasks) API. The task ID in this case is found
in the returned task object's `id` field.

### Examples

List the sub-folders of the `/search/path` folder:

	$ curl -u <token>:unused 'https://images.example.com/api/v1/admin/filesystem/folders/?path=/search/path'
	{
	  "data": {
	    "children": [
	      {
	        "id": 49,
	        "name": "/search/path/child1",
	        "parent_id": 44,
	        "path": "/search/path/child1",
	        "status": 0
	      },
	      {
	        "id": 45,
	        "name": "/search/path/child2",
	        "parent_id": 44,
	        "path": "/search/path/child2",
	        "status": 1
	      }
	    ],
	    "id": 44,
	    "name": "/search/path",
	    "parent": {
	      "id": 42,
	      "name": "/search",
	      "parent_id": 1,
	      "path": "/search",
	      "status": 1
	    },
	    "parent_id": 42,
	    "path": "/search/path",
	    "status": 1
	  },
	  "message": "OK",
	  "status": 200
	}

Create a new folder `/test_images/mynewfolder`:

	$ curl -X POST -u <token>:unused -F 'path=/test_images/mynewfolder/' 'https://images.example.com/api/v1/admin/filesystem/folders/'
	{
	  "data": {
	    "id": 3,
	    "name": "/test_images/mynewfolder",
	    "parent_id": 2,
	    "path": "/test_images/mynewfolder",
	    "status": 1
	  },
	  "message": "OK",
	  "status": 200
	}

Delete the folder that was just created:

	$ curl -X DELETE -u <token>:unused 'https://images.example.com/api/v1/admin/filesystem/folders/3/'
	{
	  "data": {
	    "id": 3,
	    "name": "/test_images/mynewfolder",
	    "parent_id": 2,
	    "path": "/test_images/mynewfolder",
	    "status": 0
	  },
	  "message": "OK",
	  "status": 200
	}

If the operation takes more than 30 seconds, status `202` and an ongoing task
object are returned. In this case the task ID is the object's `id` field, so
`288` in this example:

	$ curl -X PUT -u <token>:unused -F 'path=/renamed-large-folder' 'https://images.example.com/api/v1/admin/filesystem/folders/23/'
	{
	  "data": {
	    "error_log_level": "error",
	    "funcname": "move_folder",
	    "id": 288,
	    "keep_for": 10,
	    "keep_until": null,
	    "lock_id": "6008_1",
	    "log_level": "info",
	    "name": "Move disk folder ID 23",
	    "params": {
	      "folder_id": 23,
	      "path": "/renamed-large-folder"
	    },
	    "priority": 10,
	    "result": null,
	    "status": 1,
	    "user": {
	      "allow_api": true,
	      "auth_type": 1,
	      "email": "matt@quru.com",
	      "first_name": "Matt",
	      "id": 2,
	      "last_name": "Fozard",
	      "status": 1,
	      "username": "matt"
	    },
	    "user_id": 2
	  },
	  "message": "OK task accepted",
	  "status": 202
	}

<a name="api_tasks"></a>
## system tasks
Initiates or polls the status of a background task.

### URL
* `/api/v1/admin/tasks/[function name]/` for `POST`
* `/api/v1/admin/tasks/[task id]/` for `GET`

### Supported methods
* `GET`
* `POST`

### Parameters
* None for `GET`
* Parameters for `POST` are specific to the task function:
	* Function `purge_system_stats` - physically deletes system-level statistics older than
	  a given date
		* `before_time` - Mandatory, text - Date in format 'yyyy-mm-dd' beyond which the
		  system statistics should be purged
	* Function `purge_image_stats` - physically deletes image-level statistics older than
	  a given date
		* `before_time` - Mandatory, text - Date in format 'yyyy-mm-dd' beyond which the
		  image statistics should be purged
	* Function `purge_deleted_folder_data` - physically deletes image and folder data that
	  are only marked as _deleted_ (this includes archived image audit trails)
		* `path` - Mandatory, text - The folder path in which to purge (recursively) the
		  _deleted_ database records. Specify the root folder `/` to purge everything.

### Permissions required
* Either super user or
* For `GET`, the user that owns the task

### Returns
The task object including its status, or `null` if the task has completed and
no longer exists.

The following task status values exist:

* `0` - New, awaiting processing
* `1` - In progress
* `2` - Complete, with the (task dependent) return value inside the `result` attribute

Once complete, a task will remain in the database so that a duplicate task cannot
run again for `keep_for` seconds (until `keep_until` time UTC is reached).
If `keep_for` is `0` (and `keep_until` is `null`), the task will be deleted within
a few seconds of completion, after which a status `404` will be returned when that
task is requested.

### Example

Get the task with ID `301`:

	$ curl -u <token>:unused 'https://images.example.com/api/v1/admin/tasks/301/'
	{
	  "data": {
	    "error_log_level": "error",
	    "funcname": "purge_deleted_folder_data",
	    "id": 301,
	    "keep_for": 0,
	    "keep_until": null,
	    "lock_id": null,
	    "log_level": "info",
	    "name": "Purge deleted data",
	    "params": {
	      "folder_id": 2
	    },
	    "priority": 20,
	    "result": null,
	    "status": 2,
	    "user": {
	      "allow_api": true,
	      "auth_type": 1,
	      "email": "matt@quru.com",
	      "first_name": "Matt",
	      "id": 2,
	      "last_name": "Fozard",
	      "status": 1,
	      "username": "matt"
	    },
	    "user_id": 2
	  },
	  "message": "OK",
	  "status": 200
	}

Then trying again after a few seconds:

	$ curl -u <token>:unused 'https://images.example.com/api/v1/admin/tasks/301/'
	{
	  "data": null,
	  "message": "The requested item was not found (301)",
	  "status": 404
	}
