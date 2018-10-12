#
# Quru Image Server
#
# Document:      helpers.py
# Date started:  12 Oct 2018
# By:            Matt Fozard
# Purpose:       Image server API helper functions
# Requires:      Flask
# Copyright:     Quru Ltd (www.quru.com)
# Licence:
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published
#   by the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see http://www.gnu.org/licenses/
#
# Last Changed:  $Date$ $Rev$ by $Author$
#
# Notable modifications:
# Date       By    Details
# =========  ====  ============================================================
#

from imageserver.flask_app import data_engine, image_engine, permissions_engine
from imageserver.flask_util import external_url_for
from imageserver.models import FolderPermission, Image
from imageserver.portfolios.util import get_portfolio_image_attrs
from imageserver.session_manager import get_session_user
from imageserver.util import filepath_filename, get_file_extension
from imageserver.views_util import url_for_image_attrs


def _prep_image_object(image, can_download=None, **url_params):
    """
    Modifies an Image object to add calculated fields.
    This provides the common data dictionary for the file admin, image admin,
    image details, upload, and directory listing (with detail) APIs.

    If the download permission is None, it is calculated for the image's folder
    and the current user. The permissions engine returns this from cache when
    possible, but it is more efficient to pass in the permission if it is already
    known, or when handling many images in the same folder.

    If any url_params are provided (as kwargs), these are included in the
    generated image 'url' attribute.
    """
    if can_download is None:
        can_download = permissions_engine.is_folder_permitted(
            image.folder,
            FolderPermission.ACCESS_DOWNLOAD,
            get_session_user()
        )
    image.url = external_url_for('image', src=image.src, **url_params)
    image.download = can_download
    image.filename = filepath_filename(image.src)
    # Unsupported files shouldn't be in the database but it can happen if
    # support is removed for a file type that was once enabled
    image.supported = (
        get_file_extension(image.filename) in
        image_engine.get_image_formats(supported_only=True)
    )
    return image


def _prep_blank_image_object():
    """
    Returns a blank image object with the same fields as _prep_image_object()
    but with all empty/zero values.
    """
    image = Image('', None, '', '', 0, 0, 0)
    image.id = 0
    image.folder_id = 0
    image.url = ''
    image.download = False
    image.filename = ''
    image.supported = False
    return image


def _prep_folio_object(folio):
    """
    Modifies a Folio object to add calculated fields.
    """
    # Add attribute for public viewing URL
    folio.url = external_url_for('folios.portfolio_view', human_id=folio.human_id)
    # Add extra fields to the images
    if data_engine.attr_is_loaded(folio, 'images'):
        folio.images = [
            _prep_folioimage_object(fi) for fi in folio.images
        ]
    # Add extra fields to the downloads
    if data_engine.attr_is_loaded(folio, 'downloads'):
        folio.downloads = [
            _prep_folioexport_object(folio, fe) for fe in folio.downloads
        ]
    return folio


def _prep_folioimage_object(folioimage):
    """
    Modifies a FolioImage object to add calculated fields.
    """
    # Add an attribute for the image URL with portfolio-specific image parameters
    folioimage.url = url_for_image_attrs(
        get_portfolio_image_attrs(folioimage, validate=False),
        external=True
    )
    folioimage.image = _prep_image_object(folioimage.image)
    return folioimage


def _prep_folioexport_object(folio, folioexport):
    """
    Modifies a FolioExport object to add calculated fields.
    """
    # Add attribute for the download URL
    if folioexport.filename:
        folioexport.url = external_url_for(
            'folios.portfolio_download',
            human_id=folio.human_id,
            filename=folioexport.filename
        )
    else:
        folioexport.url = ''
    return folioexport
