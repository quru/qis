from abc import ABCMeta
import ldap #@UnresolvedImport

# LDAP settings
class LDAP_settings:

    # fields and their defaults
    #
    f_uri = "ldap://192.168.2.233"
    f_base = "dc=opensusepdc,dc=quru,dc=com"
    f_scope = ldap.SCOPE_SUBTREE

    # bind credentials, if required
    #f_bind_dn = "cn=james bond,cn=users,dc=ad2008,dc=quru,dc=com"
    #f_bind_password = "hotelcalifornia"

# LDAP backend interface
class LDAP_backend:
    __metaclass__ = ABCMeta

    # fields
    f_last_error_desc = ""
    f_last_error_info = ""

    # instantiating LDAP settings object
    f_LDAP_settings = LDAP_settings()

    def check_OU(self, p_user_session, p_OU):
        # (string operation)
        # better way to check case insensitively?
        if p_user_session.get_LDAP_DN().lower().endswith(p_OU.lower()):
            p_user_session.set_authorised(True)
            return True
        else:
            p_user_session.set_authorised(False)
            return False

    def get_last_error_desc(self):
        return self.f_last_error_desc

    def get_last_error_info(self):
        return self.f_last_error_info

# OpenLDAP abstract implementation
class LDAP_backend_OpenLDAP(LDAP_backend):
    __metaclass__ = ABCMeta

    # initialising LDAP connection in the constructor
    #
    def __init__(self):
        try:
            # ISSUE! global? why not field?
            global g_LDAP_connection
            g_LDAP_connection = ldap.initialize(self.f_LDAP_settings.f_uri)
            g_LDAP_connection.simple_bind_s()
        except ldap.LDAPError as (l_desc, l_info):
            # ISSUE! correct way to handle exception and then do something about them, like exit perhaps?
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def get_all_groups(self):
        l_LDAP_attributes = ["dn", "cn", "gidNumber", "member"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(objectClass=posixGroup)", l_LDAP_attributes)
            return l_result
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def get_all_OUs(self):
        l_LDAP_attributes = ["dn", "ou"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(objectClass=organizationalUnit)", l_LDAP_attributes)
            return l_result
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info    

    def discover_dn(self, p_user_session):
        l_LDAP_attributes = ["dn"]
        try:
            global g_LDAP_connection            
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(&(objectClass=posixAccount)(uid=" + p_user_session.get_username() + "))", l_LDAP_attributes)

            if len(l_result) == 0:
                p_user_session.set_authenticated(False)
                return

            p_user_session.set_LDAP_DN(l_result[0][0])
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def bind(self, p_user_session):
        self.discover_dn(p_user_session)

        if p_user_session.get_LDAP_DN() == None:
            p_user_session.set_authenticated(False)
            return            

        try:
            l_ldap_connection = ldap.initialize(self.f_LDAP_settings.f_uri)
            l_ldap_connection.simple_bind_s(p_user_session.get_LDAP_DN(), p_user_session.get_password())
            # in the case of this directory server, the bind does not fail if the credentials were incorrect
            # so, a manual check is required by comparing bind's properties with what the user had supplied
            # (string operation)
            # better way to compare case insensitively?
            if l_ldap_connection.whoami_s().lower() == "dn:" + p_user_session.get_LDAP_DN().lower():
                p_user_session.set_authenticated(True)

                # take the opportunity to load other interesting attributes of the user
                self.load_attributes(p_user_session)
            else:
                # mark the authentication failed if our manual compare fails
                p_user_session.set_authenticated(False)

        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def load_attributes(self, p_user_session):
        l_LDAP_attributes = ["uidNumber", "gidNumber", "uid", "cn", "givenName", "sn"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(&(objectClass=posixAccount)(uid=" + p_user_session.get_username() + "))", l_LDAP_attributes)
            p_user_session.set_LDAP_attributes(l_result[0][1])
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def check_group(self, p_user_session, p_gid):
        if p_user_session.get_LDAP_DN() == None:
            self.discover_dn(p_user_session)

        if int(p_user_session.get_LDAP_attribute("gidNumber")[0]) == p_gid:
            p_user_session.set_authorised(True)
        else:
            l_LDAP_attributes = ["dn", "gidNumber"]
            try:
                global g_LDAP_connection
                l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(&(objectClass=posixGroup)(member=" + p_user_session.get_LDAP_DN() + "))", l_LDAP_attributes)

                if len(l_result) == 0:
                    p_user_session.set_authorised(False)
                    return

                if int(l_result[0][1]["gidNumber"][0]) == p_gid:
                    p_user_session.set_authorised(True)
                else:
                    p_user_session.set_authorised(False)

            except ldap.LDAPError as (l_desc, l_info):
                f_last_error_desc = l_desc
                f_last_error_info = l_info
                
# OpenLDAP PDC implementation
class LDAP_backend_OpenLDAP_PDC(LDAP_backend_OpenLDAP):
    pass

# Apple LDAP implementation
class LDAP_backend_Apple(LDAP_backend):

    # initialising LDAP connection in the constructor
    #
    def __init__(self):
        try:
            # ISSUE! global? why not field?
            global g_LDAP_connection
            g_LDAP_connection = ldap.initialize(self.f_LDAP_settings.f_uri)
            g_LDAP_connection.simple_bind_s()
        except ldap.LDAPError as (l_desc, l_info):
            # ISSUE! correct way to handle exception and then do something about them, like exit perhaps?
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def get_all_groups(self):
        l_LDAP_attributes = ["dn", "cn", "gidNumber", "apple-generateduid", "apple-group-realname", "apple-group-memberguid", "description"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(objectClass=apple-group)", l_LDAP_attributes)
            return l_result
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def get_all_OUs(self):
        l_LDAP_attributes = ["dn", "cn"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(objectClass=container)", l_LDAP_attributes)
            return l_result
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info    

    def discover_dn(self, p_user_session):
        l_LDAP_attributes = ["dn"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(&(objectClass=apple-user)(uid=" + p_user_session.get_username() + "))", l_LDAP_attributes)

            if len(l_result) == 0:
                p_user_session.set_authenticated(False)
                return

            p_user_session.set_LDAP_DN(l_result[0][0])
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def bind(self, p_user_session):
        self.discover_dn(p_user_session)

        if p_user_session.get_LDAP_DN() == None:
            p_user_session.set_authenticated(False)
            return            

        try:
            l_ldap_connection = ldap.initialize(self.f_LDAP_settings.f_uri)
            l_ldap_connection.simple_bind_s(p_user_session.get_LDAP_DN(), p_user_session.get_password())
            # in the case of this directory server, the bind does not fail if the credentials were incorrect
            # so, a manual check is required by comparing bind's properties with what the user had supplied
            # (string operation)
            # better way to compare case insensitively?
            if l_ldap_connection.whoami_s().lower() == "dn:" + p_user_session.get_LDAP_DN().lower:
                p_user_session.set_authenticated(True)

                # take the opportunity to load other interesting attributes of the user
                self.load_attributes(p_user_session)
            else:
                # mark the authentication failed if our manual compare fails
                p_user_session.set_authenticated(False)

        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def load_attributes(self, p_user_session):
        l_LDAP_attributes = ["uidNumber", "apple-generateduid", "gidNumber", "uid", "cn", "givenName", "sn"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(&(objectClass=apple-user)(uid=" + p_user_session.get_username() + "))", l_LDAP_attributes)
            p_user_session.set_LDAP_attributes(l_result[0][1])
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def check_group(self, p_user_session, p_gid):
        if p_user_session.get_LDAP_DN() == None:
            self.discover_dn(p_user_session)

        if int(p_user_session.get_LDAP_attribute("gidNumber")[0]) == p_gid:
            p_user_session.set_authorised(True)
        else:
            l_LDAP_attributes = ["dn", "gidNumber"]
            try:
                global g_LDAP_connection
                l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(&(objectClass=apple-group)(apple-group-memberguid=" + p_user_session.get_LDAP_attribute("apple-generateduid")[0] + "))", l_LDAP_attributes)

                if len(l_result) == 0:
                    p_user_session.set_authorised(False)
                    return

                if int(l_result[0][1]["gidNumber"][0]) == p_gid:
                    p_user_session.set_authorised(True)
                else:
                    p_user_session.set_authorised(False)

            except ldap.LDAPError as (l_desc, l_info):
                f_last_error_desc = l_desc
                f_last_error_info = l_info

# Windows 2008 R2 LDAP implementation
class LDAP_backend_Windows2008R2(LDAP_backend):

    # initialising LDAP connection in the constructor
    #
    def __init__(self):
        try:
            # ISSUE! global? why not field?
            global g_LDAP_connection
            g_LDAP_connection = ldap.initialize(self.f_LDAP_settings.f_uri)
            g_LDAP_connection.simple_bind_s(self.f_LDAP_settings.f_bind_dn, self.f_LDAP_settings.f_bind_password)
        except ldap.LDAPError as (l_desc, l_info):
            # ISSUE!
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def get_all_groups(self):
        l_LDAP_attributes = ["dn", "cn", "primaryGroupToken"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(objectClass=group)", l_LDAP_attributes)
            return l_result
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def get_all_OUs(self):
        l_LDAP_attributes = ["dn", "ou"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(objectClass=organizationalUnit)", l_LDAP_attributes)
            return l_result
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info    

    def discover_dn(self, p_user_session):
        l_LDAP_attributes = ["distinguishedName"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(&(objectClass=user)(sAMAccountName=" + p_user_session.get_username() + "))", l_LDAP_attributes)

            if len(l_result) == 0:
                p_user_session.set_authenticated(False)
                return

            p_user_session.set_LDAP_DN(l_result[0][0])

        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def bind(self, p_user_session):
        self.discover_dn(p_user_session)

        if p_user_session.get_LDAP_DN() == None:
            p_user_session.set_authenticated(False)
            return            

        try:
            l_ldap_connection = ldap.initialize(self.f_LDAP_settings.f_uri)
            # in the case of this directory server, the bind fails with incorrect credentials
            l_ldap_connection.simple_bind_s(p_user_session.get_LDAP_DN(), p_user_session.get_password())
            p_user_session.set_authenticated(True)
            # take the opportunity to load other interesting attributes of the user
            self.load_attributes(p_user_session)

        except ldap.LDAPError as (l_desc, l_info):
            # exception caused by bind failure, mark authentication failed here
            p_user_session.set_authenticated(False)
            self.f_last_error_desc = l_desc
            self.f_last_error_info = l_info

    def load_attributes(self, p_user_session):
        l_LDAP_attributes = ["primaryGroupID", "cn", "givenName", "sn"]
        try:
            global g_LDAP_connection
            l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(&(objectClass=user)(sAMAccountName=" + p_user_session.get_username() + "))", l_LDAP_attributes)
            p_user_session.set_LDAP_attributes(l_result[0][1])
        except ldap.LDAPError as (l_desc, l_info):
            f_last_error_desc = l_desc
            f_last_error_info = l_info

    def check_group(self, p_user_session, p_gid):
        if p_user_session.get_LDAP_DN() == None:
            self.discover_dn(p_user_session)

        if int(p_user_session.get_LDAP_attribute("primaryGroupID")[0]) == p_gid:
            p_user_session.set_authorised(True)
        else:
            l_LDAP_attributes = ["distinguishedName", "primaryGroupToken"]
            try:
                global g_LDAP_connection
                l_result = g_LDAP_connection.search_s(self.f_LDAP_settings.f_base, self.f_LDAP_settings.f_scope, "(&(objectClass=group)(member=" + str(p_user_session.get_LDAP_DN()) + "))", l_LDAP_attributes)

                if len(l_result) == 0:
                    p_user_session.set_authorised(False)
                    return

                p_user_session.set_authorised(False)
                for l_each_result in l_result:
                    # introduced a try to get around "TypeError: list indices must be integers, not str" exceptions
                    try:
                        if(int(l_each_result[1]["primaryGroupToken"][0]) == p_gid):
                            p_user_session.set_authorised(True)
                            return
                    except:
                        pass                

            except ldap.LDAPError as (l_desc, l_info):
                f_last_error_desc = l_desc
                f_last_error_info = l_info

# user session object
class User_session:

    # user's input fields
    #
    # f_username
    # f_password

    # user session status fields
    #
    f_authenticated = None
    f_authorised = None

    # ldap fields
    #
    f_LDAP_attributes = {}
    f_LDAP_DN = None

    def __init__(self, p_username, p_password):
        self.f_username = p_username
        self.f_password = p_password

    def get_username(self):
        return self.f_username

    def get_password(self):
        return self.f_password

    def set_LDAP_DN(self, p_LDAP_DN):
        self.f_LDAP_DN = p_LDAP_DN

    def get_LDAP_DN(self):
        return self.f_LDAP_DN

    def set_LDAP_attributes(self, p_value):
        self.f_LDAP_attributes.update(p_value)

    def get_LDAP_attribute(self, p_LDAP_attribute):
        return self.f_LDAP_attributes[p_LDAP_attribute]

    def get_LDAP_attributes(self):
        return self.f_LDAP_attributes

    def set_authenticated(self, p_authenticated):
        self.f_authenticated = p_authenticated

        # nulling the password for security in any case
        self.f_password = None

    def get_authenticated(self):
        return self.f_authenticated

    def set_authorised(self, p_authorised):
        self.f_authorised = p_authorised

    def get_authorised(self):
        return self.f_authorised

# main
def main():

    # some OO setup tasks
    LDAP_backend.register(LDAP_backend_Apple)
    LDAP_backend.register(LDAP_backend_Windows2008R2)
    LDAP_backend.register(LDAP_backend_OpenLDAP)
    LDAP_backend.register(LDAP_backend_OpenLDAP_PDC)

    # instantiating the user session object
    l_user_session = User_session("margaret.thatcher", "hotelcalifornia")

    something = LDAP_backend_OpenLDAP_PDC()

    something.bind(l_user_session)
    
    if l_user_session.get_authenticated():
        something.check_group(l_user_session, 1000)
    
    print l_user_session.get_authenticated()
    print l_user_session.get_authorised()

    if l_user_session.get_authenticated():
        something.check_OU(l_user_session, "ou=people,dc=opensusepdc,dc=quru,dc=com")
    
    print l_user_session.get_authenticated()
    print l_user_session.get_authorised()

    #print l_user_session.get_LDAP_DN()

    #print something.get_all_groups()

    #print something.get_all_OUs()

    #print something.get_last_error_desc()
    #print something.get_last_error_info()

# go!
main()

