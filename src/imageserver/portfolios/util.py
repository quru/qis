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

from imageserver.errors import ServerTooBusyError
from imageserver.filesystem_manager import (
    count_files, delete_file, delete_dir, path_exists,
    get_portfolio_directory, get_portfolio_export_file_path
)
from imageserver.flask_app import data_engine, task_engine
from imageserver.image_attrs import ImageAttrs
from imageserver.models import FolioHistory, Task, FolioExport


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


def delete_portfolio_export(folio_export, history_user, history_info, _db_session=None):
    """
    Deletes a portfolio export record and the associated zip file (if it exists),
    and adds an audit trail entry for the parent portfolio. If you supply a
    database session it will be committed before the zip file is deleted, so
    that files are only deleted once the database operations are known to have
    worked.

    Raises a ServerTooBusyError if the export is still in progress.
    Raises an OSError if the zip file or directory cannot be deleted.
    """
    db_session = _db_session or data_engine.db_get_session()
    try:
        # Ensure we can access folio_export.portfolio
        if not data_engine.object_in_session(folio_export, db_session):
            folio_export = data_engine.get_object(
                FolioExport, folio_export.id, _db_session=db_session
            )

        # Check whether the export task is running
        if folio_export.task_id:
            task = task_engine.get_task(folio_export.task_id, _db_session=db_session)
            if (task and task.status == Task.STATUS_ACTIVE) or (
                task and task.status == Task.STATUS_PENDING and
                not task_engine.cancel_task(task)
            ):
                raise ServerTooBusyError(
                    'this export is currently in progress, wait a while then try again'
                )

        # Delete and add history in one commit
        data_engine.add_portfolio_history(
            folio_export.portfolio,
            history_user,
            FolioHistory.ACTION_UNPUBLISHED,
            history_info,
            _db_session=db_session,
            _commit=False
        )
        data_engine.delete_object(
            folio_export,
            _db_session=db_session,
            _commit=True
        )
        # If we got this far the database delete worked and we now need to
        # delete the exported zip file
        zip_rel_path = get_portfolio_export_file_path(folio_export)
        if folio_export.filename:
            delete_file(zip_rel_path)
        # And if the zip directory is now empty, delete the directory too
        zip_rel_dir = get_portfolio_directory(folio_export.portfolio)
        if path_exists(zip_rel_dir, require_directory=True):
            zips_count = count_files(zip_rel_dir, recurse=False)
            if zips_count[0] == 0:
                delete_dir(zip_rel_dir)
    finally:
        if not _db_session:
            db_session.close()
