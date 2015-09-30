#
# Quru Image Server
#
# Document:      template_attrs.py
# Date started:  12 May 2011
# By:            Matt Fozard
# Purpose:       Wrapper for an image template definition
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

from image_attrs import ImageAttrs
from util import validate_boolean, validate_number


class TemplateAttrs(object):
    """
    Class to hold an image template definition, that is a set of desired image
    attributes together with optional handling settings.
    """
    # The template fields that are not part of ImageAttrs
    __attrs = ['expiry_secs', 'attachment', 'record_stats']

    def __init__(self, image_attrs, expiry_secs=None, attachment=None, record_stats=None):
        """
        Constructs a new template object.
        See the ImageAttrs class and this class's methods for allowed parameter values.
        """
        self.image_attrs = image_attrs
        self.image_attrs.normalise_values()
        self._expiry_secs = expiry_secs
        self._attachment = attachment
        self._record_stats = record_stats

    @staticmethod
    def from_dict(name, attr_dict):
        """
        Returns a new TemplateAttrs, populated from the given dictionary
        and validated. This is the opposite of to_dict().
        Raises a ValueError if any of the dictionary values fail validation.
        """
        new_obj = TemplateAttrs(ImageAttrs(name))
        new_obj.apply_dict(attr_dict, True, True)
        return new_obj

    def to_dict(self):
        """
        Returns a dictionary of fields and values represented by this object.
        This is the opposite of from_dict().
        """
        dct = self.image_attrs.to_dict()
        for attr in TemplateAttrs.__attrs:
            dct[attr] = getattr(self, "_%s" % attr)
        return dct

    def apply_dict(self, attr_dict, override_values=True, validate=True):
        """
        Applies a set template attributes to this object from a dictionary.
        If override_values is False, each new attribute value will only
        be applied if there is no existing value for that attribute.
        Raises a ValueError if any of the dictionary values fail validation.
        """
        self.image_attrs.apply_dict(attr_dict, override_values, validate=False)
        for attr in TemplateAttrs.__attrs:
            dict_val = attr_dict.get(attr)
            if dict_val is not None and dict_val != '':
                obj_key = "_%s" % attr
                if override_values or getattr(self, obj_key) is None:
                    setattr(self, obj_key, dict_val)
        if validate:
            self.validate()

    def expiry_secs(self):
        """
        Returns the maximum number of seconds a client should cache an image for
        (0 for default handling, -1 to never cache), or None if the template
        does not specify a value.
        """
        return self._expiry_secs

    def attachment(self):
        """
        Returns True if the image should be served as an attachment (invoking
        the Save File As dialog in a web browser), False if the image should be
        served inline (the default), or None if the template does not specify a value.
        """
        return self._attachment

    def record_stats(self):
        """
        Returns True if the image should be included in system statistics,
        False if not, or None if the template does not specify a value.
        """
        return self._record_stats

    def validate(self):
        """
        Validates that all image attributes and handling settings, if they have
        been given a value, are within allowed limits. This method raises a
        ValueError if a value is invalid, otherwise returns with no value.
        """
        self.image_attrs.validate()
        try:
            field_name = 'expiry_secs'
            if self._expiry_secs is not None:
                validate_number(self._expiry_secs, -1, 31536000)
            field_name = 'attachment'
            if self._attachment is not None:
                validate_boolean(self._attachment)
            field_name = 'record_stats'
            if self._record_stats is not None:
                validate_boolean(self._record_stats)
        except ValueError as e:
            raise ValueError('%s: %s' % (field_name, str(e)))
