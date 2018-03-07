#
# Quru Image Server
#
# Unit test settings
#

# Yes we are
TESTING = True

# Test the production code
DEBUG = False

# Use separate testing databases
CACHE_DATABASE_CONNECTION = "postgresql+psycopg2:///qis-cache-test"
CACHE_DATABASE_POOL_SIZE = 2
MGMT_DATABASE_CONNECTION = "postgresql+psycopg2:///qis-mgmt-test"
MGMT_DATABASE_POOL_SIZE = 2

# Set testing image directories
INSTALL_DIR = "../"
DOCS_BASE_DIR = INSTALL_DIR + "doc/"
ICC_BASE_DIR = INSTALL_DIR + "icc/"
IMAGES_BASE_DIR = INSTALL_DIR + "images/"
LOGGING_BASE_DIR = INSTALL_DIR + "logs/"

# Export portfolios to a separate directory that is safe to delete
FOLIO_EXPORTS_DIR = '.test_folio_exports'

# Test automatic PDF bursting
PDF_BURST_TO_PNG = True
PDF_BURST_DPI = 150

# Don't run stats tidy tasks
STATS_KEEP_DAYS = 0

# No HTTPS
INTERNAL_BROWSING_SSL = False
SESSION_COOKIE_SECURE = False

# No LDAP
LDAP_INTEGRATION = False

# No usage stats
USAGE_DATA_URL = ""
