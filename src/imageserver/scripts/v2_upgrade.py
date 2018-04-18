#
# Quru Image Server
#
# Document:      v2_upgrade.py
# Date started:  07 Sep 2015
# By:            Matt Fozard
# Purpose:       QIS v1 to v2 upgrade script
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
# 05Nov2015  Matt  Change from template upgrade to whole version upgrade
# 17Aug2016  Matt  v2.2 Move IMAGE_DEFAULT settings into a default template
#
# Notes:
#
# Usage: sudo -u qis python v2_upgrade.py
#

import configparser
import glob
import os
import signal
import site
import shutil
import sys


# Utility to allow no value for a config file option
def _config_get(cp, get_fn, section, option, lower_case=False):
    if cp.has_option(section, option):
        val = get_fn(section, option)
        return val.lower() if lower_case else val
    else:
        return None


def upgrade_cache_table():
    log('Loading QIS engine...')
    from imageserver.flask_app import cache_engine
    try:
        log('\nUpgrading cache tracking database table')
        cache_engine.clear()
        cache_engine._drop_db_schema()
        cache_engine._create_db_schema()
        log('Cache tracking database table upgraded OK')
    except Exception as e:
        log('Warning: failed to upgrade cache database table: ' + str(e))


def import_templates():
    from imageserver.flask_app import app, data_engine
    from imageserver.image_attrs import ImageAttrs
    from imageserver.models import ImageTemplate
    from imageserver.template_attrs import TemplateAttrs
    from imageserver.util import filepath_filename, parse_colour

    # Find *.cfg
    num_files = 0
    num_errors = 0
    num_skipped = 0
    template_dir_path = app.config.get(
        'TEMPLATES_BASE_DIR',
        os.path.join(app.config['INSTALL_DIR'], 'templates')
    )
    cfg_files = glob.glob(os.path.join(template_dir_path, '*.cfg'))
    log('Starting image templates import')

    merge_def_settings = False
    if cfg_files:
        merge_conf = input(
            '\nQIS v2 removes the system settings for default image format, '
            'quality, DPI, strip, colorspace, and expiry time. These values '
            'now need to be defined in your image templates instead. '
            'Do you want to merge these settings into your templates now? '
            'Y/N (Y recommended)\n'
        )
        merge_def_settings = (merge_conf in ['y', 'Y'])

    for cfg_file_path in cfg_files:
        num_files += 1
        (template_name, _) = os.path.splitext(filepath_filename(cfg_file_path))
        try:
            # Read config file
            cp = configparser.RawConfigParser()
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
            t_expiry = _config_get(cp, cp.getint, section, 'expiry')
            t_attach = _config_get(cp, cp.getboolean, section, 'attach')

            # Get the template as a dict
            template_dict = {
                'expiry_secs': {'value': t_expiry},
                'attachment': {'value': t_attach},
                'record_stats': {'value': t_stats}
            }
            ia_dict = t_image_attrs.to_dict()
            template_dict.update(dict(
                (k, {'value': v}) for k, v in ia_dict.items()
                if k not in ['filename', 'template']
            ))
            # Apply the obsolete default image settings to it
            if merge_def_settings:
                if not template_dict['format']['value']:
                    template_dict['format']['value'] = app.config.get('IMAGE_FORMAT_DEFAULT')
                if not template_dict['quality']['value']:
                    template_dict['quality']['value'] = app.config.get('IMAGE_QUALITY_DEFAULT')
                if template_dict['strip']['value'] is None:
                    template_dict['strip']['value'] = app.config.get('IMAGE_STRIP_DEFAULT')
                if not template_dict['colorspace']['value']:
                    template_dict['colorspace']['value'] = app.config.get('IMAGE_COLORSPACE_DEFAULT')
                if not template_dict['dpi_x']['value']:
                    template_dict['dpi_x']['value'] = app.config.get('IMAGE_DPI_DEFAULT')
                if not template_dict['dpi_y']['value']:
                    template_dict['dpi_y']['value'] = app.config.get('IMAGE_DPI_DEFAULT')
                if template_dict['expiry_secs']['value'] is None:
                    template_dict['expiry_secs']['value'] = app.config.get('IMAGE_EXPIRY_TIME_DEFAULT', 60 * 60 * 24 * 7)
            # Record stats needs to default to True in v2.2+
            if template_dict['record_stats']['value'] is None:
                template_dict['record_stats']['value'] = True
            # Create the TemplateAttrs object
            template_attrs = TemplateAttrs(template_name, template_dict)

            # Validate
            template_attrs.validate()

            # Import template if it doesn't exist already
            existing_obj = data_engine.get_image_template(tempname=template_name)
            if existing_obj is None:
                log('Importing template \'%s\'' % template_name)
                data_engine.save_object(ImageTemplate(
                    template_name,
                    'Imported template',
                    template_attrs.get_raw_dict()
                ))
            else:
                log('Skipped template \'%s\' as it already exists' % template_name)
                num_skipped += 1

        except Exception as e:
            log('Failed to import template \'%s\' due to: %s' % (template_name, str(e)))
            num_errors += 1

    log('Template import complete, %d file(s) found, '
        '%d errors, %d skipped.' % (num_files, num_errors, num_skipped))

    if not merge_def_settings:
        log('Warning: You chose not to merge your v1 default image settings '
            'into your v2 templates. Since the default image settings are '
            'now ignored, some images may be rendered differently.')

    deleted = False
    if num_errors == 0 and os.path.exists(template_dir_path):
        conf = input('\nThe old template files are no longer required. ' +
                         'Do you want to remove them now? Y/N\n')
        if conf in ['y', 'Y']:
            log('Removing directory ' + template_dir_path)
            try:
                shutil.rmtree(template_dir_path)
                log('Old templates removed OK')
                deleted = True
            except Exception as e:
                log('Warning: failed to delete directory: ' + str(e))

    if num_files > 0 and not deleted:
        log('Info: Old template files remain in ' + template_dir_path)


def create_default_template():
    from imageserver.flask_app import app, data_engine
    from imageserver.models import ImageTemplate, Property

    log('Creating default image template')

    existing_obj = data_engine.get_image_template(tempname='Default')
    if existing_obj is None:
        data_engine.save_object(ImageTemplate(
            'Default',
            'Defines the system defaults for image generation if the '
            'image does not specify a template or specific parameter value', {
                'format': {'value': app.config.get('IMAGE_FORMAT_DEFAULT', '')},
                'quality': {'value': app.config.get('IMAGE_QUALITY_DEFAULT', 80)},
                'strip': {'value': app.config.get('IMAGE_STRIP_DEFAULT', True)},
                'colorspace': {'value': app.config.get('IMAGE_COLORSPACE_DEFAULT', 'RGB')},
                'dpi_x': {'value': app.config.get('IMAGE_DPI_DEFAULT', None)},
                'dpi_y': {'value': app.config.get('IMAGE_DPI_DEFAULT', None)},
                'record_stats': {'value': True},
                'expiry_secs': {'value': app.config.get('IMAGE_EXPIRY_TIME_DEFAULT',
                                                        60 * 60 * 24 * 7)}
            }
        ))
        log(
            'Info: Default image generation settings have been moved into a '
            'new template called \'Default\'.'
        )
    else:
        log('Skipped creation of a \'Default\' template as it already exists.')

    data_engine.save_object(Property(Property.DEFAULT_TEMPLATE, 'default'))
    log(
        'If you have any of the following settings in your local_settings.py '
        'file, they can now be deleted:\n\n'
        'IMAGE_FORMAT_DEFAULT\nIMAGE_QUALITY_DEFAULT\nIMAGE_STRIP_DEFAULT\n'
        'IMAGE_COLORSPACE_DEFAULT\nIMAGE_DPI_DEFAULT\nIMAGE_EXPIRY_TIME_DEFAULT\n'
    )


def log(astr):
    print(astr)


if __name__ == '__main__':
    try:
        pver = sys.version_info
        # Pythonpath - escape sub-folder and add custom libs
        site.addsitedir('../..')
        site.addsitedir('../../../lib/python%d.%d/site-packages' % (pver.major, pver.minor))
        # Get confirmation
        print('This utility will upgrade your QIS v1.x installation to v2.')
        conf = input('To proceed, type Y and press [Enter].\n')
        if conf not in ['y', 'Y']:
            print('Cancelled')
            exit(1)
        # Go
        upgrade_cache_table()
        import_templates()
        create_default_template()
        print('Upgrade complete. Review the messages above for any errors, ' + \
              'warnings, or manual changes required.')
        exit(0)

    except KeyboardInterrupt:
        print('\nCancelled')
        exit(1)
    except Exception as e:
        print('Utility exited with error:\n' + str(e))
        print('Common issues:')
        print('Are you running as the qis user?')
        print('Do you need to set the QIS_SETTINGS environment variable?')
    finally:
        # Also stop any background processes we started
        signal.signal(signal.SIGTERM, lambda a, b: None)
        os.killpg(os.getpgid(0), signal.SIGTERM)
        print('')
