/** @odoo-module **/

import { VippsPOSPaymentScreen } from "./pos_payment_screen";
import { registry } from "@web/core/registry";

// Register the Vipps POS Payment Screen
registry.category("pos_screens").add("VippsPOSPaymentScreen", VippsPOSPaymentScreen);

// Register the XML template
import { templates } from "@web/core/assets";
templates.VippsPOSPaymentScreen = "VippsPOSPaymentScreen";