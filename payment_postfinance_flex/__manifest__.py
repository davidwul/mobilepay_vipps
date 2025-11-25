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
    'name': 'PostFinance Checkout Flex',
    'category': 'Payment Gateway',
    'version': '18.0.4.0.0',
    'description': """PostFinance Checkout Flex Payment Provider""",
    'currency': 'EUR',
    'price': 150,
    'license': 'Other proprietary',
    'author': 'PIT Solutions AG',
    'website': 'http://www.pitsolutions.com/',
    'depends': ['payment', 'website_payment', 'pits_payment_provider_base'],
    'external_dependencies': {
        'python': ['cairosvg', 'postfinancecheckout']
    },
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        'views/payment_postfinance_templates.xml',
        'views/payment_method_views.xml',
        'data/payment_provider_data.xml',
        'data/email_template_data.xml',
        'data/ir_cron_data.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_frontend': [
            'payment_postfinance_flex/static/src/xml/**/*',
            'payment_postfinance_flex/static/src/js/**/*',
        ]
    }
}
