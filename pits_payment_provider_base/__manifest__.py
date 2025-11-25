# -*- coding: utf-8 -*-
#################################################################################
# Author      : PIT Solutions AG. (<https://www.pitsolutions.com/>)
# Copyright(c): 2019 - Present PIT Solutions AG.
# License URL : https://www.webshopextension.com/en/licence-agreement/
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://www.webshopextension.com/en/licence-agreement/>
#################################################################################

{
    'name': 'PITS Payment Provider Base',
    'version': '18.0.1.0.0',
    'category': 'Payment',
    'summary': 'Base module for payment provider functionality',
    'description': """Provides common payment provider functionality like logging and chatter""",
    'license': 'Other proprietary',
    'author': 'PIT Solutions AG',
    'website': 'https://www.pitsolutions.com',
    'depends': ['website_payment', 'mail'],
    'data': [
        'data/ir_cron_data.xml',
        'security/ir.model.access.csv',
        'views/payment_provider_log_views.xml',
        'views/res_config_settings_views.xml',
        'views/payment_transaction_views.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False
}
