#
# Quru Image Server
#
# Document:      util.py
# Date started:  09 Mar 2018
# By:            Matt Fozard
# Purpose:       Portfolio utility functions
# Requires:
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

from imageserver.image_attrs import ImageAttrs


def _template_dict_to_kv_dict(template_dict):
    """
    Converts a dictionary in the template definition format:
        {"width": { "value": 800 }, ...}
    to the plain key/value dictionary format:
        {"width": 800, ...}

    This should be the same operation as doing:
        TemplateAttrs('', template_dict).get_values_dict() or
        TemplateAttrs('', template_dict).get_image_attrs().to_dict()

    But it is implemented separately here because the TemplateAttrs methods
    perform a ton of extra wasted work that we don't need to do here.
    """
    try:
        # TODO Use a dictionary comprehension in the python3 branch (here and in TemplateAttrs)
        return dict((k, template_dict[k]['value']) for k in template_dict)
    except (KeyError, TypeError):
        raise ValueError('Bad template dictionary format (refer to portfolio image parameters)')


def get_portfolio_image_attrs(folio_image, normalise=True, validate=True):
    """
    Creates and returns the ImageAttrs object for a FolioImage object. You can
    use this to obtain a binary image file (via ImageManager) or the image URL
    (via views_util.url_for_image_attrs()).

    If folio_image.parameters is empty, the returned ImageAttrs object
    will only have the 'filename' attribute set.

    Raises a ValueError if validation is requested and folio_image.parameters
    contains a bad value.
    """
    image_attrs = ImageAttrs(folio_image.image.src, folio_image.image.id)
    if folio_image.parameters:
        image_attrs.apply_dict(
            _template_dict_to_kv_dict(folio_image.parameters),
            override_values=False,
            validate=validate,
            normalise=normalise
        )
    return image_attrs


def get_portfolio_export_image_attrs(folio_export, folio_image, normalise=True, validate=True):
    """
    Creates and returns the ImageAttrs object for a FolioImage object in the
    context of the given FolioExport. You can use this to obtain a binary image
    file (via ImageManager) or the image URL (via views_util.url_for_image_attrs()).

    The export's image parameters are applied on top of the single image parameters.

    Raises a ValueError if validation is requested and either
    folio_export.parameters or folio_image.parameters contains a bad value.
    """
    if folio_export.originals:
        return ImageAttrs(folio_image.image.src, folio_image.image.id)

    image_attrs = get_portfolio_image_attrs(folio_image, False, False)
    if folio_export.parameters:
        image_attrs.apply_dict(
            _template_dict_to_kv_dict(folio_export.parameters),
            override_values=True,
            validate=False,
            normalise=False
        )
    if normalise:
        image_attrs.normalise_values()
    if validate:
        image_attrs.validate()
    return image_attrs
