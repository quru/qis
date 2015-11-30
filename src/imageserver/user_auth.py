#
# Quru Image Server
#
# Document:      user_auth.py
# Date started:  10 Aug 2011
# By:            Matt Fozard
# Purpose:       Image server user authentication module
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

import ldap_client

from errors import AuthenticationError
from flask_app import app
from models import User
from util import generate_password


def authenticate_user(username, password, data_engine, logger):
    """
    Authenticates the given user credentials, returning the associated User
    object on success, or None if either the username or password is incorrect.

    If LDAP integration is enabled, a new image server user account will be
    created if there is no existing account but the username and password are
    valid on the LDAP server.

    An AuthenticationError is raised if an error occurrs performing the
    authentication process.
    """
    try:
        logger.debug('Authenticating user \'' + username + '\'')
        user = data_engine.get_user(username=username)

        if user is not None:
            if user.auth_type == User.AUTH_TYPE_PASSWORD:
                # Standard authentication
                auth = user.check_password(password)
                auth_type = 'Standard'
            elif user.auth_type == User.AUTH_TYPE_LDAP:
                # LDAP authentication
                auth, _ = _authenticate_ldap(username, password, logger)
                auth_type = 'LDAP'
            else:
                raise AuthenticationError('Unsupported authentication type')

            logger.debug(
                auth_type + ' authentication ' + ('OK' if auth else 'failed') +
                ' for \'' + username + '\''
            )
            # Return result for known username
            return user if auth else None
        else:
            # The username is not known locally
            if app.config['LDAP_INTEGRATION']:
                logger.debug('Checking LDAP server for unknown user \'' + username + '\'')
                auth, user_attrs = _authenticate_ldap(username, password, logger)
                if auth:
                    # Valid LDAP user, auto-create a new user account
                    logger.debug(
                        'Identified user \'' + username + '\' on LDAP server, ' +
                        'authentication OK, creating new user account'
                    )
                    logger.debug('User details: ' + str(user_attrs))
                    (firstname, lastname) = _get_firstname_lastname(user_attrs)
                    new_user = User(
                        firstname,
                        lastname,
                        '',
                        username,
                        generate_password(),  # This won't get used...
                        User.AUTH_TYPE_LDAP,  # as long as this flag still says LDAP
                        False,
                        User.STATUS_ACTIVE
                    )
                    data_engine.create_user(new_user)
                    return new_user
                else:
                    logger.debug('LDAP authentication failed for \'' + username + '\'')
                    return None

            # Unknown username
            logger.debug('Unknown user \'' + username + '\'')
            return None

    except AuthenticationError as e:
        raise
    except Exception as e:
        raise AuthenticationError(str(e))


def _get_firstname_lastname(ldap_user_attrs):
    """
    Returns a tuple of (forename, surname) from the supplied dictionary of
    user attributes. This is taken from the cn attribute is possible, otherwise
    the givenName and sn attributes.
    """
    cn = ldap_user_attrs.get('cn', ['Unknown'])[0]
    gn = ldap_user_attrs.get('givenName', ['Unknown'])[0]
    sn = ldap_user_attrs.get('sn', ['Unknown'])[0]
    parts = cn.split(' ')
    if len(parts) == 2:
        gn = parts[0]
        sn = parts[1]
    return (gn.capitalize(), sn.capitalize())


def _authenticate_ldap(username, password, logger):
    """
    Authenticates the given username and password against the configured LDAP
    server. Returns a tuple indicating success and the user's LDAP attributes,
    so either (True, { user attrs }) or (False, None).
    The returned LDAP attributes are server-specific and have format
    { 'attr_name': ['attr_value_1', ...] }

    An AuthenticationError is raised if an LDAP server is not configured or
    if it could not be contacted.
    """
    if not app.config['LDAP_INTEGRATION']:
        raise AuthenticationError('LDAP integration is disabled')
    if not app.config['LDAP_SERVER'] or not app.config['LDAP_SERVER_TYPE']:
        raise AuthenticationError('LDAP authentication has not been configured')
    if not ldap_client.ldap_installed:
        raise AuthenticationError('LDAP support is not installed')
    if app.config['LDAP_SECURE'] and not ldap_client.ldap_tls_installed:
        raise AuthenticationError('TLS support for LDAP is not installed (e.g. OpenSSL)')

    try:
        # Get LDAP config
        ldap_type = app.config['LDAP_SERVER_TYPE'].lower()
        ldap_config = ldap_client.LDAP_Settings(
            app.config['LDAP_SERVER'],
            app.config['LDAP_SECURE'],
            app.config['LDAP_QUERY_BASE'],
            app.config['LDAP_BIND_USER_DN'],
            app.config['LDAP_BIND_PASSWORD']
        )
        # Create correct client type
        if ldap_type == 'openldapposix':
            ldap_engine = ldap_client.OpenLDAP_Client(ldap_config, True)
        elif ldap_type == 'openldaporganizational':
            ldap_engine = ldap_client.OpenLDAP_Client(ldap_config, False)
        elif ldap_type == 'apple':
            ldap_engine = ldap_client.AppleLDAP_Client(ldap_config)
        elif ldap_type == 'activedirectory':
            ldap_engine = ldap_client.Windows2008R2_Client(ldap_config)
        else:
            raise AuthenticationError('Unsupported LDAP type: ' + app.config['LDAP_SERVER_TYPE'])

        # Try authentication
        auth = ldap_engine.authenticate_user(username, password)
        if auth:
            # Success, return user info too
            user_attrs = ldap_engine.get_user_attributes(username)
            return (True, user_attrs)

        # Rejected
        return (False, None)

    except ldap_client.LDAP_Error as e:
        logger.error(
            'LDAP error authenticating user \'' + username + '\': ' +
            e.type_name + ': ' +
            e.desc + ((' (' + e.info + ')') if e.info else '')
        )
        raise AuthenticationError(e.desc)
