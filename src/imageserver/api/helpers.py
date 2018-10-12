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

from imageserver.flask_app import data_engine
from imageserver.flask_util import external_url_for
from imageserver.views_util import url_for_image_attrs
from imageserver.portfolios.util import get_portfolio_image_attrs


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
    # Add attribute for the image viewing URL
    folioimage.url = url_for_image_attrs(
        get_portfolio_image_attrs(folioimage, validate=False),
        external=True
    )
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
