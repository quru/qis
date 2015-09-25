#
# Quru Image Server
#
# Document:      import_templates.py
# Date started:  07 Sep 2015
# By:            Matt Fozard
# Purpose:       QIS v1 to v2 template converter
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
#
# Notes:
#
# Usage: sudo -u qis python import_templates.py
#

import ConfigParser
import glob
import os
import signal
import site


# Utility to allow no value for a config file option
def _config_get(cp, get_fn, section, option, lower_case=False):
    if cp.has_option(section, option):
        val = get_fn(section, option)
        return val.lower() if lower_case else val
    else:
        return None


def import_templates():
    log('\nThis utility imports QIS v1 image templates into the QIS v2 database')
    raw_input('Press [Enter] to continue, or Ctrl-C to exit now.\n')

    log('Loading QIS engine...')
    from imageserver.flask_app import app, data_engine
    from imageserver.image_attrs import ImageAttrs
    from imageserver.models import ImageTemplate
    from imageserver.template_attrs import TemplateAttrs
    from imageserver.util import filepath_filename, parse_colour

    # Find *.cfg
    num_files = 0
    cfg_files = glob.glob(unicode(os.path.join(app.config['INSTALL_DIR'], 'templates', '*.cfg')))
    log('')
    for cfg_file_path in cfg_files:
        num_files += 1
        (template_name, _) = os.path.splitext(filepath_filename(cfg_file_path))
        try:
            # Read config file
            cp = ConfigParser.RawConfigParser()
            cp.read(cfg_file_path)

            # Get image values and put them in an ImageAttrs object
            section = 'ImageAttributes'
            t_image_attrs = ImageAttrs(
                template_name,
                -1,
                _config_get(cp, cp.getint, section, 'page'),
                _config_get(cp, cp.get, section, 'format', True),
                None,
                _config_get(cp, cp.getint, section, 'width'),
                _config_get(cp, cp.getint, section, 'height'),
                _config_get(cp, cp.get, section, 'halign', True),
                _config_get(cp, cp.get, section, 'valign', True),
                _config_get(cp, cp.getfloat, section, 'angle'),
                _config_get(cp, cp.get, section, 'flip'),
                _config_get(cp, cp.getfloat, section, 'top'),
                _config_get(cp, cp.getfloat, section, 'left'),
                _config_get(cp, cp.getfloat, section, 'bottom'),
                _config_get(cp, cp.getfloat, section, 'right'),
                _config_get(cp, cp.getboolean, section, 'autocropfit'),
                _config_get(cp, cp.getboolean, section, 'autosizefit'),
                parse_colour(_config_get(cp, cp.get, section, 'fill')),
                _config_get(cp, cp.getint, section, 'quality'),
                _config_get(cp, cp.getint, section, 'sharpen'),
                _config_get(cp, cp.get, section, 'overlay', False),
                _config_get(cp, cp.getfloat, section, 'ovsize'),
                _config_get(cp, cp.get, section, 'ovpos', True),
                _config_get(cp, cp.getfloat, section, 'ovopacity'),
                _config_get(cp, cp.get, section, 'icc', True),
                _config_get(cp, cp.get, section, 'intent', True),
                _config_get(cp, cp.getboolean, section, 'bpc'),
                _config_get(cp, cp.get, section, 'colorspace', True),
                _config_get(cp, cp.getboolean, section, 'strip'),
                _config_get(cp, cp.getint, section, 'dpi'),
                None
            )
            t_image_attrs.normalise_values()

            # Get misc options
            section = 'Miscellaneous'
            t_stats = _config_get(cp, cp.getboolean, section, 'stats')

            # Get handling options and create the TemplateAttrs object
            section = 'BrowserOptions'
            template_attrs = TemplateAttrs(
                t_image_attrs,
                _config_get(cp, cp.getint, section, 'expiry'),
                _config_get(cp, cp.getboolean, section, 'attach'),
                t_stats
            )

            # Validate
            template_attrs.validate()

            # Import template if it doesn't exist already
            existing_obj = data_engine.get_image_template(tempname=template_name)
            if existing_obj is None:
                log('Importing template \'%s\'' % template_name)
                data_engine.save_object(ImageTemplate(
                    template_name,
                    '',
                    template_attrs.to_dict()
                ))
            else:
                log('Skipped template \'%s\' as it already seems to be imported' % template_name)

        except Exception as e:
            log('Failed to import template \'%s\' due to: %s' % (template_name, str(e)))

    log('Import complete, %d file(s) processed' % num_files)


def log(astr):
    print astr


if __name__ == '__main__':
    try:
        # Pythonpath - escape sub-folder and add custom libs
        site.addsitedir('../..')
        site.addsitedir('../../../lib/python2.6/site-packages')
        site.addsitedir('../../../lib/python2.7/site-packages')
        # Go
        import_templates()
        exit(0)

    except KeyboardInterrupt:
        print '\nCancelled'
        exit(1)
    except Exception as e:
        print 'Utility exited with error:\n' + str(e)
        print 'Ensure you are using the correct user account, ' \
              'and (optionally) set the QIS_SETTINGS environment variable.'
    finally:
        # Also stop any background processes we started
        signal.signal(signal.SIGTERM, lambda a, b: None)
        os.killpg(os.getpgid(0), signal.SIGTERM)
