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
# 05Nov2015  Matt  v2 Change template values to be expandable objects
#

from image_attrs import BooleanValidator, RangeValidator, ImageAttrs


class TemplateAttrs(object):
    """
    Class to hold an image template definition,
    that is a reusable set of image attributes, handling options, and meta data.
    The attribute names are the same as those defined for ImageAttrs,
    plus extra handling fields:

      expiry_secs - suggested HTTP caching period
      attachment - whether to flag as HTTP download instead of inline
      record_stats - whether to record image level usage stats

    The expected dictionary format is currently:
    {
        "width": { "value": 800 },
        "flip": { "value": "v" },
        "attachment": { "value": False },
    }
    Later versions are expected to add new elements alongside "value".
    """
    def __init__(self, name, template_dict=None):
        """
        Constructs a new template object,
        optionally populated from the given dictionary and validated.
        Raises a ValueError if any of the dictionary values fail validation.
        """
        self._name = name
        if template_dict:
            self._set_template_dict(template_dict)
        else:
            self._template = {}
            self._image_attrs = ImageAttrs(name)
            self._memo_values = None

    def _set_template_dict(self, template_dict):
        """
        Sets this template from the content of a dictionary as described in the
        class documentation. Raises a ValueError if any of the dictionary
        values fail validation.
        """
        # Start with provisional values
        self._template = template_dict.copy()
        self._image_attrs = ImageAttrs(self._name)
        self._memo_values = None
        try:
            # We need to populate our ImageAttrs from a raw key/value dict
            raw_dict = dict((k, v['value']) for (k, v) in self._template.iteritems())
        except (KeyError, TypeError):
            raise ValueError('Bad template dictionary format (refer to TemplateAttrs)')
        # Set normalise=False so that we keep all assigned template values
        #     otherwise e.g. fill=white, page=1 would be removed
        self._image_attrs.apply_dict(raw_dict, True, validate=False, normalise=False)
        # Now ImageAttrs did round the floats and lower case (many of) the strings.
        # A few places rely on this, so we need to copy the changed values back again.
        raw_dict = self.get_values_dict()
        for (k, v) in raw_dict.iteritems():
            if k in self._template:
                self._template[k]['value'] = v
            elif v is not None:
                self._template[k] = {'value': v}
        # Finally validate the result
        self.validate()

    def get_template_dict(self):
        """
        Returns the full template definition as a dictionary as described in
        the class documentation. This may differ from the dictionary originally
        provided in the constructor, e.g. by containing "blank" entries and
        normalised values. Do not modify the returned object.
        """
        return self._template

    def get_values_dict(self):
        """
        Returns a dictionary of the field/value pairs defined by this template.
        This dictionary is compatible with the to_dict() and from_dict() methods
        of ImageAttrs, but also includes the additional fields described in the
        class documentation. Do not modify the returned object.
        """
        if self._memo_values is None:
            dct = self._image_attrs.to_dict()
            for attr in TemplateAttrs.validators().iterkeys():
                dct[attr] = self._get_value(attr, False)
            self._memo_values = dct
        return self._memo_values

    def get_image_attrs(self):
        """
        Returns an ImageAttrs object containing only the image attributes and values
        specified by this template. The extra template-only fields are not included.
        Do not modify the returned object.
        """
        return self._image_attrs

    def name(self):
        """
        Returns this template's name.
        """
        return self._name

    def expiry_secs(self):
        """
        Returns the maximum number of seconds a client should cache an image for
        (0 for default handling, -1 to never cache), or None if the template
        does not specify a value.
        """
        return self._get_value('expiry_secs', False)

    def attachment(self):
        """
        Returns True if the image should be served as an attachment (invoking
        the Save File As dialog in a web browser), False if the image should be
        served inline (the default), or None if the template does not specify a value.
        """
        return self._get_value('attachment', False)

    def record_stats(self):
        """
        Returns True if the image should be included in system statistics,
        False if not, or None if the template does not specify a value.
        """
        return self._get_value('record_stats', False)

    def _get_value(self, field_name, lowercase):
        """
        Returns a single field value from the template dictionary,
        or None if the field name is not present.
        """
        tv = self._template.get(field_name)
        val = tv['value'] if tv else None
        if val and lowercase:
            val = val.lower()
        return val

    @staticmethod
    def validators():
        """
        Returns a dictionary mapping the internal field names of
        this class to a value validation class and web parameter name.
        E.g. { "expiry_secs": (RangeValidator(-1, 31536000), "expires"),
               "attachment": (BooleanValidator(), "attach"), ... }
        """
        return {
            "expiry_secs": (RangeValidator(-1, 31536000), "expires"),
            "attachment": (BooleanValidator(), "attach"),
            "record_stats": (BooleanValidator(), "stats")
        }

    def validate(self):
        """
        Validates that all image attributes and handling settings, if they have
        been given a value, are within allowed limits. This method raises a
        ValueError if a value is invalid, otherwise returns with no value.
        """
        self._image_attrs.validate()
        try:
            field_name = ''
            for field_name, val_tuple in TemplateAttrs.validators().iteritems():
                validator = val_tuple[0]
                val = self._get_value(field_name, False)
                if val is not None:
                    validator(val)
        except ValueError as e:
            raise ValueError('%s: %s' % (field_name, str(e)))
