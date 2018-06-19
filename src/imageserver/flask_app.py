#
# Quru Image Server
#
# Document:      flask_app.py
# Date started:  03 Oct 2011
# By:            Matt Fozard
# Purpose:       Flask app initializer
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

import os
import signal

import flask
from . import __about__


def extend_app(app):
    """
    Applies custom extensions and middleware to the Flask app.
    """
    from . import csrf
    from . import flask_ext
    # Add proxy server support, if required
    if app.config['PROXY_SERVERS'] > 0:
        flask_ext.add_proxy_server_support(app, app.config['PROXY_SERVERS'])
    # Fix URLs with a badly encoded query string
    flask_ext.fix_bad_query_strings(app)
    # Add Markdown support to templates
    flask_ext.install_markdown_template_tag(app, app.config['DOCS_BASE_DIR'])
    # Enhanced JSON support for the API
    flask_ext.enhance_json_encoder(app)
    # We'll measure request times for our stats
    flask_ext.time_requests(app, True)
    # In development, allow any origin. In production this is set in the web server config.
    if app.config['DEBUG']:
        flask_ext.add_cors_headers(app, '*')
    # We need HTTP authentication for the API
    flask_ext.install_http_authentication(app, app.config['API_AUTHENTICATION_CLASS'])
    # And CSRF protection for the web pages (this needs to be after the http auth)
    csrf.install_csrf(app)


def configure_app(app):
    """
    Applies the configuration settings for the Flask app.
    This is the sum of the Flask defaults, overridden by conf.base_settings,
    overridden by the file specified in the QIS_SETTINGS environment variable.
    If QIS_SETTINGS is empty, the application tries ../../conf/local_settings.py
    """
    _ENV_VAR = 'QIS_SETTINGS'

    # Set Jinja template engine options
    app.jinja_options = app.jinja_options.copy()
    app.jinja_options['trim_blocks'] = True
    app.jinja_options['lstrip_blocks'] = True

    # Apply base configuration
    configs_used = ['base_settings']
    app.config.from_object('imageserver.conf.base_settings')

    # Examine QIS_SETTINGS
    env_settings = os.environ.get(_ENV_VAR)
    if not env_settings:
        # See if local_settings.py exists
        app_src_path = os.path.split(__file__)[0]
        local_settings_path = os.path.abspath(
            os.path.join(app_src_path, '..', '..', 'conf', 'local_settings.py')
        )
        if os.path.exists(local_settings_path):
            env_settings = os.environ[_ENV_VAR] = local_settings_path

    # Apply the user configuration
    if env_settings:
        if env_settings.endswith(".py"):
            # Full path to a Python settings file (the common case)
            app.config.from_envvar(_ENV_VAR)
            configs_used.append(os.path.split(env_settings)[1])
        else:
            # Name of a Python file in the imageserver.conf package
            app.config.from_object('imageserver.conf.' + env_settings)
            configs_used.append(env_settings)

    app.config['_SETTINGS_IN_USE'] = ' + '.join(configs_used)


def reconfigure_app_for_imaging_backend(app):
    """
    Disables and warns about settings enabled in app.config that are not supported
    by the installed imaging back end.
    """
    supported_files = app.image_engine.get_image_formats(supported_only=True)
    supported_ops = app.image_engine.get_supported_operations()
    if app.config['IMAGE_RESIZE_GAMMA_CORRECT'] and not supported_ops.get('resize_gamma', False):
        app.config['IMAGE_RESIZE_GAMMA_CORRECT'] = False
        app.log.warning(
            'Disabled IMAGE_RESIZE_GAMMA_CORRECT as it is not supported by the imaging library'
        )
    if app.config['PDF_BURST_TO_PNG'] and 'pdf' not in supported_files:
        app.config['PDF_BURST_TO_PNG'] = False
        app.log.warning(
            'Disabled PDF_BURST_TO_PNG as it is not supported by the imaging library'
        )


# Create main web app
app = flask.Flask(__name__)
configure_app(app)
extend_app(app)

with app.app_context():
    from .cache_manager import CacheManager
    from .data_manager import DataManager
    from .image_manager import ImageManager
    from .log_manager import LogManager
    from .permissions_manager import PermissionsManager
    from .stats_manager import StatsManager
    from .task_manager import TaskManager

    logger = None
    try:
        # Create the logging client+server
        logger = LogManager(
            __about__.__tag__.lower() + '_' + str(os.getpid()),
            app.config['DEBUG'],
            app.config['LOGGING_SERVER'],
            app.config['LOGGING_SERVER_PORT']
        )
        app.log = logger
        LogManager.run_server(
            app.config['LOGGING_SERVER'],
            app.config['LOGGING_SERVER_PORT'],
            __about__.__tag__.lower() + '.log',
            app.config['DEBUG']
        )
        # Capture Flask's internal logging
        app.logger.addHandler(logger.logging_handler)

        # Announce startup
        logger.info(__about__.__title__ + ' v' + __about__.__version__ + ' engine startup')
        logger.info('Using settings ' + app.config['_SETTINGS_IN_USE'])
        if app.config['DEBUG']:
            logger.info('*** Debug mode ENABLED ***')
        if app.config['BENCHMARKING']:
            logger.info('*** Benchmarking mode ENABLED ***')

        # Create the stats recording client
        stats_engine = StatsManager(
            logger,
            app.config['STATS_SERVER'],
            app.config['STATS_SERVER_PORT']
        )
        app.stats_engine = stats_engine

        # Create caching engine
        cache_engine = CacheManager(
            logger,
            app.config['MEMCACHED_SERVERS'],
            app.config['CACHE_DATABASE_CONNECTION'],
            app.config['CACHE_DATABASE_POOL_SIZE']
        )
        app.cache_engine = cache_engine

        # Create database management engine
        data_engine = DataManager(
            cache_engine,
            logger,
            app.config['MGMT_DATABASE_CONNECTION'],
            app.config['MGMT_DATABASE_POOL_SIZE']
        )
        app.data_engine = data_engine

        # Create background task processing client
        task_engine = TaskManager(
            data_engine,
            logger
        )
        task_engine.init_housekeeping_tasks()
        app.task_engine = task_engine

        # Create a user permissions engine
        permissions_engine = PermissionsManager(
            data_engine,
            cache_engine,
            task_engine,
            app.config,
            logger
        )
        app.permissions_engine = permissions_engine

        # Create the main imaging engine
        image_engine = ImageManager(
            data_engine,
            cache_engine,
            task_engine,
            permissions_engine,
            app.config,
            logger
        )
        app.image_engine = image_engine
        # v4.0 Adjust configuration for supported imaging operations
        reconfigure_app_for_imaging_backend(app)

        # Import app views and template filters
        from . import views                                      # @UnusedImport
        from . import views_util                                 # @UnusedImport
        from . import views_pages                                # @UnusedImport

        # Import blueprints
        from . import api
        app.register_blueprint(api.blueprint, url_prefix='/api')

        from . import admin
        app.register_blueprint(admin.blueprint, url_prefix='/admin')

        from . import reports
        app.register_blueprint(reports.blueprint, url_prefix='/reports')

        from . import portfolios
        app.register_blueprint(portfolios.blueprint, url_prefix='/portfolios')

        # Import global template functions
        views_util.register_template_funcs()

    except Exception as e:
        # Startup error - this is fatal, but try to get the error message into our
        #                 main log file (for easier debugging) before bombing out
        if logger:
            logger.error("Error starting up: " + str(e) + "\nThe process will now exit.")
        raise


# Auto-start the aux processes when web requests come in. When this module is
# imported from other places (e.g. unit tests, the aux processes themselves),
# call launch_aux_processes() as required.
@app.before_first_request
def on_first_request():
    _launch_aux_processes(['stats', 'tasks'])  # logs already started above


# Manually starts the aux processes outside of a web server context
def launch_aux_processes():
    with app.app_context():
        _launch_aux_processes()


def _launch_aux_processes(service_list='all'):
    # Close any open server connections before forking and...
    app.data_engine._reset_pool()
    app.cache_engine._reset_pool()
    # ...spawn the requested services
    if (service_list == 'all') or ('logs' in service_list):
        LogManager.run_server(
            app.config['LOGGING_SERVER'],
            app.config['LOGGING_SERVER_PORT'],
            __about__.__tag__.lower() + '.log',
            app.config['DEBUG']
        )
    if (service_list == 'all') or ('stats' in service_list):
        StatsManager.run_server(
            app.config['STATS_SERVER'],
            app.config['STATS_SERVER_PORT'],
            app.config['DEBUG']
        )
    if (service_list == 'all') or ('tasks' in service_list):
        TaskManager.run_server(
            app.config['TASK_SERVER'],
            app.config['TASK_SERVER_PORT'],
            app.config['DEBUG']
        )


# Manually stops the aux processes
def stop_aux_processes(nicely=True):
    use_signal = signal.SIGTERM if nicely else signal.SIGKILL
    # Stop all the processes in this process group apart from the current process
    prev_handler = signal.signal(use_signal, lambda a, b: None)
    os.killpg(os.getpgid(0), use_signal)
    if prev_handler:
        signal.signal(use_signal, prev_handler)
