from . import vipps_profile_wizard
from . import payment_provider
from . import payment_provider_audit
from . import payment_transaction
from . import res_partner

# POS models temporarily disabled - uncomment when POS module is installed
# try:
#     from odoo.addons.point_of_sale.models.pos_payment_method import PosPaymentMethod
#     from . import pos_payment_method
# except ImportError:
#     # POS module not available, skip POS models
#     import logging
#     logging.getLogger(__name__).info("POS module not available - skipping POS models")
from . import vipps_api_client
from . import vipps_data_management
from . import vipps_onboarding_wizard
from . import vipps_security
from . import vipps_webhook_security
from . import vipps_data_retention