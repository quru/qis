#
# Quru Image Server
#
# Document:      ldap_client.py
# Date started:  11 Aug 2011
# By:            Dhruv Ahuja and Matt Fozard
# Purpose:       LDAP client and helper functions
# Requires:      python-ldap
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
# 30Nov2015  Matt  Added ldap.OPT_REFERRALS = 0 for Active Directory,
#                  support for TLS / ldaps
#

# Set flags for whether LDAP support is available
ldap_installed = False
ldap_tls_installed = False
try:
    import ldap
    ldap_installed = True
    ldap_tls_installed = ldap.TLS_AVAIL
except:
    pass


class LDAP_Error(Exception):
    """
    Wraps an error thrown by python-ldap, providing easier access to the embedded
    error information by providing 'type_name', 'desc' and 'info' attributes.
    """
    def __init__(self, e):
        Exception.__init__(self, str(e))
        self.type_name = type(e).__name__
        self.desc = ''
        self.info = ''
        if len(e.args) > 0:
            err_dict = e.args[0]
            if 'desc' in err_dict:
                self.desc = err_dict['desc']
            if 'info' in err_dict:
                self.info = err_dict['info']

    def __unicode__(self):
        s = self.desc
        if self.info:
            s += ' (' + self.info + ')'
        return s

    def __str__(self):
        return self.__unicode__().encode('utf-8')


class LDAP_Settings(object):
    """
    Holds connection settings and optionally bind credentials for an LDAP
    client connection.
    """
    def __init__(self, host, use_tls, base, bind_dn=None, bind_pwd=None):
        """
        Creates a set of connection settings for querying an LDAP server.

        host - the LDAP server's host name or IP address
        use_tls - boolean whether to connect as LDAPS (use TLS)
        base - the search base to use when performing all LDAP queries,
            e.g. LDAP "cn=users,dc=server,dc=company,dc=com"
            e.g. AD   "dc=company,dc=com"
        bind_dn - an optional distinguished name of a user account to use to
                  query the LDAP server,
            e.g. LDAP "uid=username,cn=users,dc=server,dc=company,dc=com"
            e.g. AD   "username@company.com"
        bind_pwd - the password to use with bind_dn

        The use of a bind dn and password is required for Microsoft Active Directory.
        """
        self.f_uri = "ldap%s://%s" % ("s" if use_tls else "", host)
        self.f_base = base
        self.f_bind_dn = bind_dn
        self.f_bind_password = bind_pwd
        self.f_scope = ldap.SCOPE_SUBTREE

        if use_tls and not ldap_tls_installed:
            raise ValueError('Secure LDAP requested but TLS is not available')


class _LDAP_Client(object):
    """
    Provides a common back end for the various supported LDAP client classes.
    """
    def __init__(self, settings):
        self.f_settings = settings
        self.f_connection = None

    def connect(self):
        """
        Connects to the LDAP server using the configured settings, raising an
        LDAP_Error on failure. This function can be called multiple times but
        will only connect once.
        """
        if self.is_connected():
            return
        try:
            self.f_connection = ldap.initialize(self.f_settings.f_uri)
            self.f_connection.set_option(ldap.OPT_REFERRALS, 0)
            if self.f_settings.f_bind_dn:
                # Bind with credentials
                self.f_connection.simple_bind_s(
                    self.f_settings.f_bind_dn,
                    self.f_settings.f_bind_password
                )
            else:
                # Bind without credentials
                self.f_connection.simple_bind_s()
        except ldap.LDAPError as e:
            raise LDAP_Error(e)

    def is_connected(self):
        return self.f_connection is not None

    def _ldap_search(self, search_filter, attr_list):
        """
        Connnects to the LDAP server and performs a search, starting from the
        configured search base and including all its descendants.

        search_filter - the criteria to apply, a string in RFC 4515 format
        attr_list - a list of attribute names to return from search matches

        On success, a list of tuples is returned, with the format
          [ (dn, { attr_name: [attr_value, ...], ... }), ... ]
        An empty list is returned if there were no search matches.

        An LDAP_Error is raised on failure.
        """
        self.connect()
        try:
            result = self.f_connection.search_s(
                self.f_settings.f_base,
                self.f_settings.f_scope,
                search_filter,
                attr_list
            )
            # v2.5.1 Check for the weird [(None, ['ldap://server/blah']), ...] negative result
            if len(result) > 0 and not result[0][0]:
                result = []
            # Add the DN if it was requested, it isn't always returned even when in attr_list
            if len(result) > 0 and "dn" in attr_list:
                attr_dict = result[0][1]
                attr_dict["dn"] = [result[0][0]]
            return result
        except ldap.LDAPError as e:
            raise LDAP_Error(e)


class OpenLDAP_Client(_LDAP_Client):
    """
    OpenLDAP client implementation.
    Note than any method may raise an LDAP_Error on failure.
    """
    def __init__(self, settings, posix_accounts=False):
        """
        Creates an OpenLDAP client configured by an LDAP_Settings object.
        If posix_accounts is True, the posixAccount objects will be queried for
        user accounts instead of the organizationalPerson objects.
        """
        _LDAP_Client.__init__(self, settings)
        self.posix_accounts = posix_accounts

    def get_all_groups(self):
        """Returns a list of posix group DNs, and selected attributes for each"""
        return self._ldap_search(
            "(objectClass=posixGroup)",
            ["dn", "cn", "gidNumber", "member"]
        )

    def get_all_OUs(self):
        """Returns a list of organizational unit DNs, and selected attributes for each"""
        return self._ldap_search(
            "(objectClass=organizationalUnit)",
            ["dn", "ou"]
        )

    def get_user_attributes(self, username):
        """
        Returns a dictionary of attributes, each having a list of values, for
        the named LDAP user account. Returns None if the username was not found
        on the LDAP server.
        """
        object_class = "posixAccount" if self.posix_accounts else "organizationalPerson"
        result = self._ldap_search(
            "(&(objectClass=" + object_class + ")(uid=" + username + "))",
            ["dn", "uidNumber", "gidNumber", "uid", "cn", "givenName", "sn"]
        )
        return result[0][1] if len(result) > 0 else None

    def authenticate_user(self, username, password):
        """
        Attempts to authenticate an LDAP username and password against the directory,
        returning True on success, or False if the username was not found or if the
        password was incorrect.
        """
        user_attrs = self.get_user_attributes(username)
        if user_attrs:
            try:
                # We found the user account. Now open a new connection as that user.
                cn = ldap.initialize(self.f_settings.f_uri)
                user_dn = user_attrs["dn"][0]
                cn.simple_bind_s(user_dn, password)
                # The bind may not fail if the credentials were incorrect, so
                # also compare the bind's DN with the user's DN.
                return cn.whoami_s().lower() in [
                    ("dn:" + user_dn.lower()),
                    ("dn: " + user_dn.lower()),
                ]
            except ldap.INVALID_CREDENTIALS:
                return False
            except ldap.LDAPError as e:
                raise LDAP_Error(e)
        return False


class AppleLDAP_Client(OpenLDAP_Client):
    """
    Apple LDAP client implementation.
    Note than any method may raise an LDAP_Error on failure.
    """
    def __init__(self, settings):
        """Creates an Apple LDAP client configured by an LDAP_Settings object."""
        OpenLDAP_Client.__init__(self, settings)

    def get_all_groups(self):
        """Returns a list of Apple group DNs, and selected attributes for each"""
        return self._ldap_search(
            "(objectClass=apple-group)",
            ["dn", "cn", "gidNumber", "apple-generateduid",
             "apple-group-realname", "apple-group-memberguid", "description"]
        )

    def get_all_OUs(self):
        """Returns a list of organizational unit DNs, and selected attributes for each"""
        return self._ldap_search(
            "(objectClass=container)",
            ["dn", "cn"]
        )

    def get_user_attributes(self, username):
        """
        Returns a dictionary of attributes, each having a list of values, for
        the named LDAP user account. Returns None if the username was not found
        on the LDAP server.
        """
        result = self._ldap_search(
            "(&(objectClass=apple-user)(uid=" + username + "))",
            ["dn", "uidNumber", "apple-generateduid", "gidNumber", "uid", "cn", "givenName", "sn"]
        )
        return result[0][1] if len(result) > 0 else None


class Windows2008R2_Client(_LDAP_Client):
    """
    Windows 2008 R2 Active Directory client implementation.
    Note than any method may raise an LDAP_Error on failure.
    """
    def __init__(self, settings):
        """Creates an OpenLDAP client configured by an LDAP_Settings object."""
        _LDAP_Client.__init__(self, settings)

    def get_all_groups(self):
        """Returns a list of user group DNs, and selected attributes for each"""
        return self._ldap_search(
            "(objectClass=group)",
            ["dn", "cn", "primaryGroupToken"]
        )

    def get_all_OUs(self):
        """Returns a list of organizational unit DNs, and selected attributes for each"""
        return self._ldap_search(
            "(objectClass=organizationalUnit)",
            ["dn", "ou"]
        )

    def get_user_attributes(self, username):
        """
        Returns a dictionary of attributes, each having a list of values, for
        the named LDAP user account. Returns None if the username was not found
        on the LDAP server.
        """
        result = self._ldap_search(
            "(&(objectClass=user)(sAMAccountName=" + username + "))",
            ["dn", "distinguishedName", "primaryGroupID", "cn", "givenName", "sn"]
        )
        return result[0][1] if len(result) > 0 else None

    def authenticate_user(self, username, password):
        """
        Attempts to authenticate an LDAP username and password against the directory,
        returning True on success, or False if the username was not found or if the
        password was incorrect.
        """
        user_attrs = self.get_user_attributes(username)
        if user_attrs:
            try:
                # We found the user account. Now open a new connection as that user.
                cn = ldap.initialize(self.f_settings.f_uri)
                user_dn = user_attrs["dn"][0]
                cn.simple_bind_s(user_dn, password)
                # Bind success == authenticated
                return True
            except ldap.INVALID_CREDENTIALS:
                return False
            except ldap.LDAPError as e:
                raise LDAP_Error(e)
        return False
