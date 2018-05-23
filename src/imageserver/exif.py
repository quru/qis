#
# Quru Image Server
#
# Document:      exif.py
# Date started:  18 Jul 2011
# By:            Matt Fozard
# Purpose:       Converts raw TIFF, EXIF, and IPTC data values to friendly readable strings
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
# Portions of this code are loosely based on parts of The Big Picture (tag lists
# and data types) under the LGPL licence, and EXIF.py (fixed tag values, string
# filtering and Ratio class) under a BSD licence.
#                 http://code.google.com/p/thebigpicture/
#                 http://sourceforge.net/projects/exif-py/
#
# Currently no attempt is made to decode the MakerNote property
# (containing further, camera manufacturer-specific information).
#
# Notable modifications:
# Date       By    Details
# =========  ====  ============================================================
# 10Dec2015  Matt  TIFF fields should be case insensitive
#

import re

from .util import parse_float, parse_int, parse_long


def _safe_string(seq):
    """
    Filters a list of ints or a string, leaving only 8 bit ASCII characters,
    and returning the result as an ASCII string.
    """
    sstr = ''
    all_zero = True
    is_string = not isinstance(seq, list)
    for c in seq:
        c = ord(c) if is_string else c
        if c != 0:
            all_zero = False
        # Screen out non-ASCII characters
        if 32 <= c and c < 256:
            sstr += chr(c)
    # If no ASCII chars, decide what to do
    if not sstr:
        if all_zero:
            return ''
        elif len(seq) > 0:
            # Return a string version of what we were given
            return seq if is_string else ', '.join(seq)
    # Return trimmed result
    return sstr.strip()


def _parse_user_comment(val):
    """
    Interprets a UserComment field value, supplied either as the raw value
    or as a string containing comma separated byte codes.
    """
    # Use the same data type conversion as the parse for field type 7
    if CHAR_LIST_REGEX.match(val):
        val = [parse_int(num) for num in val.split(',')]
    # First 8 bytes gives string encoding - ASCII, JIS, or Unicode
    encoding_char_1 = val[0:1]
    val = val[8:]
    # Decode the rest
    if not isinstance(val, list):
        # val was already a string
        return val
    else:
        # val is a list of byte codes
        encoding_char_1 = _safe_string(encoding_char_1)
        if encoding_char_1 == '' or encoding_char_1 == 'A':
            # ASCII
            return _safe_string(val)
        elif encoding_char_1 == 'J':
            # JIS
            return str(bytearray(val), 'SJIS')
        else:
            # Unicode
            return str(bytearray(val))


def _ratio_to_float_string(rstr, places=1):
    """
    Converts a string of format "5/10" to its float string equivalent,
    i.e. "0.5" with places 1, or "0.50" with places 2, etc
    """
    sep_idx = rstr.find('/')
    if sep_idx > -1:
        ratio = float(rstr[0:sep_idx]) / float(rstr[sep_idx + 1:])
    else:
        ratio = float(rstr)
    return ('%.' + str(places) + 'f') % ratio


def _ratio_to_float_string_2(rstr):
    """
    Alias for _ratio_to_float_string with a places value of 2
    """
    return _ratio_to_float_string(rstr, 2)


def _parse_gps_time(gtime):
    """
    For some retarded reason, the GPS timestamp field is split out from the date and
    supplied as 3 ratios. This function converts it back to the usual hh:mm:ss format.
    """
    parts = gtime.split(',')
    return ':'.join([_ratio_to_float_string(p.strip(), 0) for p in parts])


def _parse_gps_position(gpos):
    """
    Converts a GPS point from 3 ratio format (degrees, minutes, seconds) to
    either dd:mm:ss.sss or dd:mm.mmm:ss format. According to the EXIF spec,
    seconds can be 0 with minutes being fractional instead.
    """
    parts = gpos.split(',')
    decstr = ''
    for (idx, ratio) in enumerate(parts):
        rval = _ratio_to_float_string(ratio.strip(), 3 if idx > 0 else 0)
        # Trim trailing zeroes
        rval = rval.rstrip('0')
        if rval.endswith('.'):
            rval = rval[0:-1]
        # Ensure number is padded to 2 leading digits
        if rval.find('.') == -1:
            rval = rval.zfill(2)
        elif rval.find('.') == 1:
            rval = '0' + rval
        if idx > 0:
            decstr += ':'
        decstr += rval
    return decstr


def _gps_position_to_decimal(dms_str, direction):
    """
    Converts a geographic longitude/latitude point in the format "degrees:minutes:seconds"
    into a decimal float value. The direction value can be N or S for a latitude, or
    E or W for a longitude. E.g. "87:43:41","W" is returned as -87.728056
    Returns None if the supplied string cannot be parsed.
    """
    try:
        direction = direction.strip().upper()
        parts = dms_str.split(':')
        if len(parts) != 3:
            raise ValueError('Expected format deg:mm:ss')
        degrees = parse_float(parts[0])
        minutes = parse_float(parts[1])
        seconds = parse_float(parts[2])
        total_seconds = (minutes * 60.0) + seconds
        dec_fraction = total_seconds / 3600.0
        multiplier = -1.0 if direction in ['W', 'S'] else 1.0
        return (degrees + dec_fraction) * multiplier
    except:
        return None


# Regex to identify "1, 2, 3" type strings
CHAR_LIST_REGEX = re.compile('[0-9]+[\s]?,[\s]?')

# EXIF and IPTC data types
DATA_TYPES = {
    0: 'Proprietary',    # length 0
    1: 'Byte',           #        1
    2: 'Ascii',          #        1
    3: 'Short',          #        2
    4: 'Long',           #        4
    5: 'Ratio',          #        8
    6: 'Signed Byte',    #        1
    7: 'Undefined',      #        1 (treat as binary)
    8: 'Signed Short',   #        2
    9: 'Signed Long',    #        4
    10: 'Signed Ratio',  #        8
    15: 'Digits'         # IPTC   4
}

# Ignore these tags when processing
IGNORE_TAGS = (
    'MakerNote', 'PrintImageMatching', 'NativeDigest',
    'JPEGInterchangeFormat', 'JPEGInterchangeFormatLength',
    'Interoperability IFD Pointer', 'InteroperabilityOffset',
    'ExifOffset', 'ExifImageLength',
    # Added v3.2
    'JPEGTables', 'StripByteCounts', 'StripOffsets'
)


# Base properties class
class BaseProps(object):
    TagsCaseSensitive = True
    Tags = []
    Types = []
    TagDisplay = {}
    TagOptions = {}


# TIFF properties
class TiffProps(BaseProps):
    TagsCaseSensitive = False
    Tags  = ["ImageWidth", "ImageLength", "BitsPerSample", "Compression", "PhotometricInterpretation", "ImageDescription", "Make", "Model", "StripOffsets", "Orientation", "SamplesPerPixel", "RowsPerStrip", "StripByteCounts", "XResolution", "YResolution", "PlanarConfiguration", "PageName", "ResolutionUnit", "TransferFunction", "Software", "DateTime", "Artist", "WhitePoint", "PrimaryChromaticities", "JPEGInterchangeFormat", "JPEGInterchangeFormatLength", "YCbCrCoefficients", "YCbCrSubSampling", "YCbCrPositioning", "ReferenceBlackWhite", "IPTC-NAA", "Copyright"]
    Types = [      4,            4,               3,           3,                       3,                      2,            2,      2,            4,            3,                3,              4,               4,                 5,             5,                3,               2,              3,                3,               2,          2,         2,         5,                  5,                    4,                          4,                            5,                  3,                  3,                 5,                 7,          2]
    TagDisplay = {
        'PageName': _safe_string
    }
    TagOptions = {
        'Compression': {
            1: 'Uncompressed',
            2: 'CCITT 1D',
            3: 'T4/Group 3 Fax',
            4: 'T6/Group 4 Fax',
            5: 'LZW',
            6: 'JPEG',
            7: 'JPEG',
            8: 'Adobe Deflate',
            9: 'JBIG B&W',
            10: 'JBIG Color',
            32766: 'Next',
            32769: 'Epson ERF Compressed',
            32771: 'CCIRLEW',
            32773: 'PackBits',
            32809: 'Thunderscan',
            32895: 'IT8CTPAD',
            32896: 'IT8LW',
            32897: 'IT8MP',
            32898: 'IT8BL',
            32908: 'PixarFilm',
            32909: 'PixarLog',
            32946: 'Deflate',
            32947: 'DCS',
            34661: 'JBIG',
            34676: 'SGILog',
            34677: 'SGILog24',
            34712: 'JPEG 2000',
            34713: 'Nikon NEF Compressed',
            65000: 'Kodak DCR Compressed',
            65535: 'Pentax PEF Compressed'
        },
        'PhotometricInterpretation': {
            2: 'RGB',
            6: 'YCbCr'
        },
        'PlanarConfiguration': {
            1: 'Chunky',
            2: 'Planar'
        },
        'Orientation': {
            1: 'Horizontal (normal)',
            2: 'Mirrored horizontal',
            3: 'Rotated 180',
            4: 'Mirrored vertical',
            5: 'Mirrored horizontal then rotated 90 CCW',
            6: 'Rotated 90 CW',
            7: 'Mirrored horizontal then rotated 90 CW',
            8: 'Rotated 90 CCW'
        },
        'ResolutionUnit': {
            1: 'Not Absolute',
            2: 'Pixels/Inch (DPI)',
            3: 'Pixels/Centimeter (PPCM)'
        },
        'YCbCrPositioning': {
            1: 'Centered',
            2: 'Co-sited'
        }
    }


# EXIF properties
class ExifProps(BaseProps):
    Tags  = ["ExposureTime", "FNumber", "ExposureProgram", "SpectralSensitivity", "ISOSpeedRatings", "OECF", "ExifVersion", "DateTimeOriginal", "DateTimeDigitized", "ComponentsConfiguration", "CompressedBitsPerPixel", "ShutterSpeedValue", "ApertureValue", "BrightnessValue", "ExposureBiasValue", "MaxApertureValue", "SubjectDistance", "MeteringMode", "LightSource", "Flash", "FocalLength", "SubjectArea", "MakerNote", "UserComment", "SubSecTime", "SubSecTimeOriginal", "SubSecTimeDigitized", "FlashpixVersion", "FlashPixVersion", "ColorSpace", "PixelXDimension", "PixelYDimension", "RelatedSoundFile", "InteroperabilityVersion", "Interoperability IFD Pointer", "FlashEnergy", "SpatialFrequencyResponse", "FocalPlaneXResolution", "FocalPlaneYResolution", "FocalPlaneResolutionUnit", "SubjectLocation", "ExposureIndex", "SensingMethod", "FileSource", "SceneType", "CFAPattern", "CustomRendered", "ExposureMode", "WhiteBalance", "DigitalZoomRatio", "FocalLengthIn35mmFilm", "SceneCaptureType", "GainControl", "Contrast", "Saturation", "Sharpness", "DeviceSettingDescription", "SubjectDistanceRange", "ImageUniqueID"]
    Types = [        5,           5,            3,                   2,                   3,            7,         7,                2,                   2,                      7,                         5,                     10,                5,               10,                 10,                   5,                 5,              3,               3,         3,          5,              3,           7,            7,            2,                 2,                    2,                   7,                 7,              3,              4,                 4,                 2,                        7,                           4,                     5,                    7,                        5,                      5,                         3,                     3,                5,               3,             7,            7,             7,             3,               3,              3,                5,                     3,                     3,             5,            3,           3,            3,                    7,                     3,                   2]
    TagDisplay = {
        'FNumber': _ratio_to_float_string,
        'ExposureBiasValue': _ratio_to_float_string_2,
        'ShutterSpeedValue': _ratio_to_float_string_2,
        'ApertureValue': _ratio_to_float_string_2,
        'MaxApertureValue': _ratio_to_float_string_2,
        'SubjectDistance': _ratio_to_float_string,
        'DigitalZoomRatio': _ratio_to_float_string_2,
        'FocalLength': _ratio_to_float_string,
        'FocalLengthIn35mmFilm': _ratio_to_float_string,
        'FocalPlaneXResolution': _ratio_to_float_string_2,
        'FocalPlaneYResolution': _ratio_to_float_string_2,
        'UserComment': _parse_user_comment
    }
    TagOptions = {
        'FocalPlaneResolutionUnit': {
            1: 'Not Absolute',
            2: 'Pixels/Inch (DPI)',
            3: 'Pixels/Centimeter (PPCM)'
        },
        'ExposureProgram': {
            0: 'Unidentified',
            1: 'Manual',
            2: 'Program Normal',
            3: 'Aperture Priority',
            4: 'Shutter Priority',
            5: 'Program Creative',
            6: 'Program Action',
            7: 'Portrait Mode',
            8: 'Landscape Mode'
        },
        'ComponentsConfiguration': {
            0: '-',
            1: 'Y',
            2: 'Cb',
            3: 'Cr',
            4: 'Red',
            5: 'Green',
            6: 'Blue'
        },
        'MeteringMode': {
            0: 'Unidentified',
            1: 'Average',
            2: 'Center-weighted average',
            3: 'Spot',
            4: 'Multi-spot',
            5: 'Pattern',
            6: 'Partial'
        },
        'LightSource': {
            0: 'Unknown',
            1: 'Daylight',
            2: 'Fluorescent',
            3: 'Tungsten',
            9: 'Fine Weather',
            10: 'Flash',
            11: 'Shade',
            12: 'Daylight Fluorescent',
            13: 'Day White Fluorescent',
            14: 'Cool White Fluorescent',
            15: 'White Fluorescent',
            17: 'Standard Light A',
            18: 'Standard Light B',
            19: 'Standard Light C',
            20: 'D55',
            21: 'D65',
            22: 'D75',
            23: 'D50',
            24: 'ISO studio tungsten',
            255: 'Other'
        },
        'Flash': {
            0: 'Flash did not fire',
            1: 'Flash fired',
            5: 'Flash fired, return light not detected',
            7: 'Flash fired, return light detected',
            9: 'Flash fired, compulsory flash mode',
            13: 'Flash fired, compulsory flash mode, return light not detected',
            15: 'Flash fired, compulsory flash mode, return light detected',
            16: 'Flash did not fire, compulsory flash mode',
            24: 'Flash did not fire, auto mode',
            25: 'Flash fired, auto mode',
            29: 'Flash fired, auto mode, return light not detected',
            31: 'Flash fired, auto mode, return light detected',
            32: 'No flash available',
            65: 'Flash fired, red-eye reduction mode',
            69: 'Flash fired, red-eye reduction mode, return light not detected',
            71: 'Flash fired, red-eye reduction mode, return light detected',
            73: 'Flash fired, compulsory flash mode, red-eye reduction mode',
            77: 'Flash fired, compulsory flash mode, red-eye reduction mode, return light not detected',
            79: 'Flash fired, compulsory flash mode, red-eye reduction mode, return light detected',
            89: 'Flash fired, auto mode, red-eye reduction mode',
            93: 'Flash fired, auto mode, return light not detected, red-eye reduction mode',
            95: 'Flash fired, auto mode, return light detected, red-eye reduction mode'
        },
        'ColorSpace': {
            1: 'sRGB',
            2: 'Adobe RGB',
            65535: 'Uncalibrated'
        },
        'SensingMethod': {
            1: 'Not defined',
            2: 'One-chip color area',
            3: 'Two-chip color area',
            4: 'Three-chip color area',
            5: 'Color sequential area',
            7: 'Trilinear',
            8: 'Color sequential linear'
        },
        'FileSource': {
            1: 'Film Scanner',
            2: 'Reflection Print Scanner',
            3: 'Digital Camera'
        },
        'SceneType': {
            1: 'Directly Photographed'
        },
        'CustomRendered': {
            0: 'Normal',
            1: 'Custom'
        },
        'ExposureMode': {
            0: 'Auto Exposure',
            1: 'Manual Exposure',
            2: 'Auto Bracket'
        },
        'WhiteBalance': {
            0: 'Auto',
            1: 'Manual'
        },
        'SceneCaptureType': {
            0: 'Standard',
            1: 'Landscape',
            2: 'Portrait',
            3: 'Night'
        },
        'GainControl': {
            0: 'None',
            1: 'Low gain up',
            2: 'High gain up',
            3: 'Low gain down',
            4: 'High gain down'
        },
        'Contrast': {
            0: 'Normal',
            1: 'Soft',
            2: 'Hard'
        },
        'Saturation': {
            0: 'Normal',
            1: 'Low',
            2: 'High'
        },
        'Sharpness': {
            0: 'Normal',
            1: 'Soft',
            2: 'Hard'
        },
        'SubjectDistanceRange': {
            0: 'Unknown',
            1: 'Macro',
            2: 'Close view',
            3: 'Distant view'
        }
    }


# GPS properties
class GpsProps(BaseProps):
    Tags = ["GPSVersionID", "GPSLatitudeRef", "GPSLatitude", "GPSLongitudeRef", "GPSLongitude", "GPSAltitudeRef", "GPSAltitude", "GPSTimeStamp", "GPSSatellites", "GPSStatus", "GPSMeasureMode", "GPSDOP", "GPSSpeedRef", "GPSSpeed", "GPSTrackRef", "GPSTrack", "GPSImgDirectionRef", "GPSImgDirection", "GPSMapDatum", "GPSDestLatitudeRef", "GPSDestLatitude", "GPSDestLongitudeRef", "GPSDestLongitude", "GPSDestBearingRef", "GPSDestBearing", "GPSDestDistanceRef", "GPSDestDistance", "GPSProcessingMethod", "GPSAreaInformation", "GPSDateStamp", "GPSDifferential"]
    Types = [1, 2, 5, 2, 5, 1, 5, 5, 2, 2, 2, 5, 2, 5, 2, 5, 2, 5, 2, 2, 5, 2, 5, 2, 5, 2, 5, 7, 7, 2, 3]
    TagDisplay = {
        'GPSTimeStamp': _parse_gps_time,
        'GPSLatitude': _parse_gps_position,
        'GPSLongitude': _parse_gps_position,
        'GPSDestLongitude': _parse_gps_position,
        'GPSDestLatitude': _parse_gps_position
    }
    TagOptions = {
        'GPSAltitudeRef': {
            0: 'Above sea level',
            1: 'Below sea level'
        }
    }


# IPTC envelope properties
class IptcEnvProps(BaseProps):
    Tags = ["EnvelopeRecordVersion", "Destination", "FileFormat", "FileVersion", "ServiceIdentifier", "EnvelopeNumber", "ProductID", "EnvelopePriority", "DateSent", "TimeSent", "CodedCharacterSet", "UniqueObjectName", "ARMIdentifier", "ARMVersion"]
    Types = [3, 2, 3, 3, 2, 15, 2, 15, 15, 2, 2, 2, 3, 3]
    TagDisplay = {}
    TagOptions = {}


# IPTC application properties
class IptcAppProps(BaseProps):
    Tags = ["ApplicationRecordVersion", "ObjectTypeReference", "ObjectAttributeReference", "ObjectName", "EditStatus", "EditorialUpdate", "Urgency", "SubjectReference", "Category", "SupplementalCategories", "FixtureIdentifier", "Keywords", "ContentLocationCode", "ContentLocationName", "ReleaseDate", "ReleaseTime", "ExpirationDate", "ExpirationTime", "SpecialInstructions", "ActionAdvised", "ReferenceService", "ReferenceDate", "ReferenceNumber", "DateCreated", "TimeCreated", "DigitalCreationDate", "DigitalCreationTime", "OriginatingProgram", "ProgramVersion", "ObjectCycle", "By-line", "By-lineTitle", "City", "Sub-location", "Province-State", "Country-PrimaryLocationCode", "Country-PrimaryLocationName", "OriginalTransmissionReference", "Headline", "Credit", "Source", "CopyrightNotice", "Contact", "Caption-Abstract", "LocalCaption", "Writer-Editor", "RasterizedCaption", "ImageType", "ImageOrientation", "LanguageIdentifier", "AudioType", "AudioSamplingRate", "AudioSamplingResolution", "AudioDuration", "AudioOutcue", "JobID", "MasterDocumentID", "ShortDocumentID", "UniqueDocumentID", "OwnerID", "ObjectPreviewFileFormat", "ObjectPreviewFileVersion", "ObjectPreviewData", "ClassifyState", "SimilarityIndex", "DocumentNotes", "DocumentHistory", "ExifCameraInfo"]
    Types = [3, 2, 2, 2, 2, 15, 15, 2, 2, 2, 2, 2, 2, 2, 15, 2, 15, 2, 2, 15, 2, 15, 15, 15, 2, 15, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 15, 15, 15, 2, 2, 2, 2, 2, 2, 3, 3, 2, 2, 2, 2, 2, 2]
    TagDisplay = {}
    TagOptions = {}


# IPTC news photo properties
class IptcPhotoProps(BaseProps):
    Tags = ["NewsPhotoVersion", "IPTCPictureNumber", "IPTCImageWidth", "IPTCImageHeight", "IPTCPixelWidth", "IPTCPixelHeight", "SupplementalType", "ColorRepresentation", "InterchangeColorSpace", "ColorSequence", "ICC_Profile", "ColorCalibrationMatrix", "LookupTable", "NumIndexEntries", "ColorPalette", "IPTCBitsPerSample", "SampleStructure", "ScanningDirection", "IPTCImageRotation", "DataCompressionMethod", "QuantizationMethod", "EndPoints", "ExcursionTolerance", "BitsPerComponent", "MaximumDensityRange", "GammaCompensatedValue"]
    Types = [3, 2, 3, 3, 3, 3, 1, 3, 1, 1, None, None, None, 3, None, 1, 1, 1, 1, 4, 1, None, 1, 1, 3, 3]
    TagDisplay = {}
    TagOptions = {}


# Ratio object that reduces itself to lowest common denominator for printing
class Ratio:
    def __init__(self, num, den):
        self.num = num
        self.den = den

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        self.reduce()
        if self.den == 1:
            return str(self.num)
        return '%d/%d' % (self.num, self.den)

    def reduce(self):
        div = self.gcd(self.num, self.den)
        if div > 1:
            self.num = self.num // div
            self.den = self.den // div

    def gcd(self, a, b):
        if b == 0:
            return a
        else:
            return self.gcd(b, a % b)


def _get_prop_val(prop_handlers, prop_val):
    """
    Returns the string value of prop_val, as determined by the handlers in
    prop_handlers (use _get_prop_handlers to obtain this object)
    """
    try:
        (_, field_type, print_fn, field_options) = prop_handlers

        # Check for empty values
        if not prop_val:
            return ''

        # Use custom handler if one is set
        if print_fn:
            return print_fn(prop_val)

        if field_type:
            if field_type in (5, 10):
                # Ratios
                sep_idx = prop_val.find('/')
                if sep_idx > -1:
                    prop_val = Ratio(
                        parse_long(prop_val[0:sep_idx]),
                        parse_long(prop_val[sep_idx + 1:])
                    )
            elif field_options:
                # All those with pre-defined options are numeric, types 3, 4, or 7
                vals = prop_val.split(',')
                prop_val = ', '.join([field_options.get(parse_long(v), v) for v in vals])
            elif field_type == 7:
                # Custom encoding. Assume we have either a straight string or a
                # string of comma separated byte codes. i.e. "ABC" or "65, 66, 67"
                if CHAR_LIST_REGEX.match(prop_val):
                    prop_val = _safe_string([parse_int(num) for num in prop_val.split(',')])
                else:
                    prop_val = _safe_string(prop_val)
            else:
                # Anything else we can just convert straight to a string
                pass

        # Return the string form of whatever we now have
        return str(prop_val).strip()

    except:
        # Fall back to returning the value as-is
        return str(prop_val).strip()


def _get_prop_handlers(profile, prop_name):
    """
    Returns a tuple containing (prop_name, type_number, handler_function, value_options)
    for the property name prop_name belonging to profile 'TIFF', 'EXIF' or 'IPTC'.
    Returns None if the profile name is invalid or the property name is not recognised
    for the profile. The returned prop_name may be different to the supplied prop_name
    for profiles with case insensitive properties.
    """
    def _get_field_index(field_class, field_name):
        """
        Returns the numeric index of field_name in field_class.Tags,
        or raises a ValueError if the field was not found. The field
        name can be in any case if field_class.TagsCaseSensitive is False.
        """
        if field_class.TagsCaseSensitive:
            return field_class.Tags.index(field_name)
        else:
            if not hasattr(field_class, 'TagsLC'):
                field_class.TagsLC = [t.lower() for t in field_class.Tags]
            return field_class.TagsLC.index(field_name.lower())

    field_idx = -1
    field_class = None

    if profile == 'EXIF':
        try:
            if prop_name.startswith('GPS'):
                field_class = GpsProps
                field_idx = _get_field_index(field_class, prop_name)
            else:
                field_class = ExifProps
                field_idx = _get_field_index(field_class, prop_name)
        except ValueError:
            # The TIFF and EXIF tags seem to overlap a bit, so try TIFF
            try:
                field_class = TiffProps
                field_idx = _get_field_index(field_class, prop_name)
            except ValueError:
                # Give up
                pass
    elif profile == 'TIFF':
        try:
            field_class = TiffProps
            field_idx = _get_field_index(field_class, prop_name)
        except ValueError:
            # Give up
            pass
    elif profile == 'IPTC':
        try:
            field_class = IptcEnvProps
            field_idx = _get_field_index(field_class, prop_name)
        except ValueError:
            try:
                field_class = IptcAppProps
                field_idx = _get_field_index(field_class, prop_name)
            except ValueError:
                try:
                    field_class = IptcPhotoProps
                    field_idx = _get_field_index(field_class, prop_name)
                except ValueError:
                    # Give up
                    pass

    # Return result
    if field_class and field_idx >= 0:
        proper_name = field_class.Tags[field_idx]
        type_number = field_class.Types[field_idx]
        handlerfn = field_class.TagDisplay.get(prop_name, None)
        options = field_class.TagOptions.get(prop_name, None)
        return (proper_name, type_number, handlerfn, options)
    else:
        return None


def raw_list_to_dict(props_list, return_unknown_profiles, return_unknown_properties):
    """
    Converts a list of tuples of image profile properties in the format
    (profile_name, prop_name, raw_string_val) into a dictionary with format
    { profile_name: [ (prop_name, friendly_string_val), ... ], ... }.

    raw_string_val should be in format "str" for strings, "123" for numbers,
    "10/50" for ratios, and "83, 84, 82" for binary (representing "STR").

    If return_unknown_profiles is True, properties of unrecognised image profiles
    are returned with all property names and values unchanged. If False, they are
    all discarded.

    If return_unknown_properties is True, property names it is not known how to
    handle are returned with the property value unchanged. If False, they are
    discarded.

    Returned (known) profile names are: 'TIFF', 'EXIF', 'GPS', or 'IPTC'
    """
    ret_dict = {}
    for (profile, name, value) in props_list:
        if name not in IGNORE_TAGS:
            # Attempt to recognise the profile name
            profile = profile.upper()
            if profile in ['EXIF', 'TIFF'] or profile.startswith('IPTC'):
                # OK, we recognise the profile
                if profile.startswith('IPTC'):
                    profile = 'IPTC'
                # Get field info
                field_info = _get_prop_handlers(profile, name)
                if field_info is not None:
                    # Return known property
                    name = field_info[0]       # E.g. "make" --> "Make"
                    if name.startswith('GPS'):
                        profile = 'GPS'
                    if profile not in ret_dict:
                        ret_dict[profile] = []
                    ret_dict[profile].append((name, _get_prop_val(field_info, value)))
                elif return_unknown_properties:
                    # Return unknown property
                    if profile not in ret_dict:
                        ret_dict[profile] = []
                    ret_dict[profile].append((name, value))
            elif return_unknown_profiles:
                # Return unknown property for unknown profile
                if profile not in ret_dict:
                    ret_dict[profile] = []
                ret_dict[profile].append((name, value))
    return ret_dict


def get_exif_geo_position(exif_dict):
    """
    Returns the decimal latitude and longitude, if available, from the GPS block
    of an EXIF data dictionary.  The dictionary should have been generated by
    the raw_list_to_dict function.

    The function returns None if there is insufficient GPS information in the
    EXIF dictionary, otherwise a dictionary with format:
    { 'latitude': 0.0, 'longitude': 0.0 }
    """
    if 'GPS' in exif_dict:
        lat_val = ''
        lat_dir = ''
        long_val = ''
        long_dir = ''
        for (prop, value) in exif_dict['GPS']:
            if prop == 'GPSLatitude':
                lat_val = value
            elif prop == 'GPSLatitudeRef':
                lat_dir = value
            elif prop == 'GPSLongitude':
                long_val = value
            elif prop == 'GPSLongitudeRef':
                long_dir = value
        if lat_val and lat_dir and long_val and long_dir:
            decimal_lat = _gps_position_to_decimal(lat_val, lat_dir)
            decimal_long = _gps_position_to_decimal(long_val, long_dir)
            if decimal_lat and decimal_long:
                return {'latitude': decimal_lat, 'longitude': decimal_long}
    return None
