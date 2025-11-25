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

"""
Constants used throughout the PostFinance payment module.
This file centralizes all constant values to maintain consistency
and make updates easier across the module.
"""

# Transaction States
POSTFINANCE_TRANSACTION_STATES = [
    'CREATE',
    'PENDING',
    'CONFIRMED',
    'PROCESSING',
    'AUTHORIZED',
    'COMPLETED'
]