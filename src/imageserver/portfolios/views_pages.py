#
# Quru Image Server
#
# Document:      views_pages.py
# Date started:  09 Mar 2018
# By:            Matt Fozard
# Purpose:       Portfolio viewing and management pages
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

from flask import render_template

from imageserver.api_util import create_api_error_dict
from imageserver.errors import DoesNotExistError
from imageserver.flask_app import app, logger, data_engine, permissions_engine
from imageserver.models import FolderPermission, FolioPermission
from imageserver.portfolios import blueprint
from imageserver.session_manager import get_session_user
from imageserver.views_util import login_required, safe_error_str, url_for_image_attrs

from .util import get_portfolio_image_attrs


# Portfolios listing/home page
@blueprint.route('/')
@login_required
def portfolios_index():
    # Not sure yet whether login is required or what this page should show
    return render_template('error.html', error={
        'title': 'Not yet implemented',
        'message': 'Sorry, this page is not yet implemented.'
    }), 404


# Portfolio edit page
@blueprint.route('/<string:human_id>/edit/')
@login_required
def portfolio_edit(human_id):
    return render_template('error.html', error={
        'title': 'Not yet implemented',
        'message': 'Sorry, this page is not yet implemented.'
    }), 404


# Portfolio export/publish page
@blueprint.route('/<string:human_id>/publish/')
@login_required
def portfolio_export(human_id):
    return render_template('error.html', error={
        'title': 'Not yet implemented',
        'message': 'Sorry, this page is not yet implemented.'
    }), 404


# Portfolio view page
@blueprint.route('/<string:human_id>/')
def portfolio_view(human_id):
    try:
        # Find the portfolio
        folio = data_engine.get_portfolio(human_id=human_id, load_images=True)
        if not folio:
            raise DoesNotExistError('Portfolio \'%s\' does not exist' % human_id)

        # Ensure that the user has permission to view the portfolio
        user = get_session_user()
        permissions_engine.ensure_portfolio_permitted(
            folio,
            FolioPermission.ACCESS_VIEW,
            user
        )

        # Filter out images that the user can't view
        # so that we don't get broken images in the UI
        checked_folders = {}  # cache folders already checked
        folio_images_1 = folio.images
        folio_images_2 = []
        for fol_img in folio_images_1:
            folder_path = fol_img.image.folder.path
            if folder_path in checked_folders:
                folio_images_2.append(fol_img)
            elif permissions_engine.is_folder_permitted(
                folder_path,
                FolderPermission.ACCESS_VIEW,
                user,
                folder_must_exist=False  # though it should exist!
            ):
                checked_folders[folder_path] = True
                folio_images_2.append(fol_img)

        # Replace the original image list with the filtered one
        folio.images = folio_images_2

        # Generate the image viewing URLs, including any portfolio-specific changes
        web_view_params = {
            'format': 'jpg',
            'colorspace': 'srgb'
        }
        sizing_view_params = {
            'width': 800,
            'height': 800,
            'size_fit': True
        }
        pre_sized_images = [
            fol_img for fol_img in folio.images if fol_img.parameters and (
                ('width' in fol_img.parameters and fol_img.parameters['width']['value']) or
                ('height' in fol_img.parameters and fol_img.parameters['height']['value'])
            )
        ]
        for fol_img in folio.images:
            image_attrs = get_portfolio_image_attrs(fol_img, False, False, False)
            image_attrs.apply_dict(web_view_params, True, False, False)
            if len(pre_sized_images) == 0:
                image_attrs.apply_dict(sizing_view_params, True, False, False)
            # Here we normalise the attrs only after everything has been applied
            image_attrs.normalise_values()
            fol_img.url = url_for_image_attrs(image_attrs)

        return render_template(
            'portfolio_view.html',
            title=folio.name,
            folio=folio,
            removed_count=(len(folio_images_1) - len(folio_images_2))
        )
    except Exception as e:
        # Although this isn't a JSON API, we're still using it like a viewing API,
        # so get the correct HTTP status code to return. create_api_error_dict() also
        # logs security errors so we don't need to do that separately here.
        error_dict = create_api_error_dict(e, logger)
        if app.config['DEBUG']:
            raise
        return render_template(
            'portfolio_view.html',
            title='Portfolio',
            err_msg='This portfolio cannot be viewed: ' + safe_error_str(e)
        ), error_dict['status']
