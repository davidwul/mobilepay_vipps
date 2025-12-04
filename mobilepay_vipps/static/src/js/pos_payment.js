/** @odoo-module **/

import { PaymentInterface } from "@point_of_sale/app/payment/payment_interface";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

/**
 * Vipps/MobilePay POS Payment Interface
 * Handles Point of Sale payments with multiple initiation methods
 */
export class VippsPOSPaymentInterface extends PaymentInterface {
    setup() {
        super.setup();
        this.paymentMethod = null;
        this.pollingInterval = null;
        this.selectedFlow = 'customer_qr';
        this.customerPhone = '';
        this.paymentStatus = 'idle';
        this.qrCodeData = null;
        this.shopNumber = null;
        this.notification = useService("notification");
    }

    /**
     * Get available payment flows for this payment method
     * @returns {Array} List of available payment flows
     */
    getAvailableFlows() {
        const method = this.payment_method;
        if (!method) return [];

        const flows = [];
        
        if (method.vipps_enable_qr_flow) {
            flows.push({
                code: 'customer_qr',
                name: _t('Customer QR Code'),
                description: _t('Customer scans QR code with their mobile app'),
                icon: 'fa-qrcode'
            });
        }
        
        if (method.vipps_enable_phone_flow) {
            flows.push({
                code: 'customer_phone',
                name: _t('Customer Phone Number'),
                description: _t('Send push message to customer\'s phone'),
                icon: 'fa-mobile'
            });
        }
        
        if (method.vipps_enable_manual_flows) {
            flows.push({
                code: 'manual_shop_number',
                name: _t('Manual Shop Number'),
                description: _t('Customer enters shop number in their app'),
                icon: 'fa-keyboard-o'
            }, {
                code: 'manual_shop_qr',
                name: _t('Manual Shop QR'),
                description: _t('Customer scans shop QR code'),
                icon: 'fa-qrcode'
            });
        }
        
        return flows;
    }

    /**
     * Set the selected payment flow
     * @param {string} flowCode - The payment flow code
     */
    setPaymentFlow(flowCode) {
        this.selectedFlow = flowCode;
        this.paymentStatus = 'flow_selected';
    }

    /**
     * Set customer phone number for push message flow
     * @param {string} phone - Customer phone number
     */
    setCustomerPhone(phone) {
        this.customerPhone = phone;
    }

    /**
     * Validate phone number format
     * @param {string} phone - Phone number to validate
     * @returns {boolean} True if valid
     */
    validatePhoneNumber(phone) {
        // Basic Nordic phone number validation
        const phoneRegex = /^(\+47|0047|\+45|0045)?\s?[0-9]{8}$/;
        return phoneRegex.test(phone.replace(/\s/g, ''));
    }

    /**
     * Send payment request to Vipps/MobilePay
     * @param {string} cid - Customer ID
     * @returns {Promise<boolean>} Success status
     */
    async send_payment_request(cid) {
        try {
            this.paymentStatus = 'processing';
            
            // Validate flow-specific requirements
            if (this.selectedFlow === 'customer_phone') {
                if (!this.customerPhone || !this.validatePhoneNumber(this.customerPhone)) {
                    this.notification.add(_t("Please enter a valid phone number"), {
                        type: "danger"
                    });
                    this.paymentStatus = 'error';
                    return false;
                }
            }

            // Get the current order and payment line
            const order = this.pos.get_order();
            const paymentLine = order.selected_paymentline;
            
            if (!paymentLine) {
                this.notification.add(_t("No payment line selected"), {
                    type: "danger"
                });
                this.paymentStatus = 'error';
                return false;
            }

            // Prepare payment data
            const paymentData = {
                amount: paymentLine.amount,
                currency: this.pos.currency.name,
                reference: order.name,
                flow: this.selectedFlow,
                customer_phone: this.customerPhone,
                pos_session_id: this.pos.pos_session.id,
            };

            // Call backend to create payment
            const result = await this.env.services.rpc({
                model: 'payment.transaction',
                method: 'create_pos_payment',
                args: [paymentData],
            });

            if (result.success) {
                this.paymentStatus = 'waiting';
                this.qrCodeData = result.qr_code;
                this.shopNumber = result.shop_number;
                
                // Start polling for payment status
                this.startStatusPolling(result.transaction_id);
                
                return true;
            } else {
                this.notification.add(result.error || _t("Payment creation failed"), {
                    type: "danger"
                });
                this.paymentStatus = 'error';
                return false;
            }

        } catch (error) {
            console.error("Vipps payment request failed:", error);
            this.notification.add(_t("Payment request failed"), {
                type: "danger"
            });
            this.paymentStatus = 'error';
            return false;
        }
    }

    /**
     * Start polling payment status
     * @param {number} transactionId - Transaction ID to poll
     */
    startStatusPolling(transactionId) {
        const pollInterval = (this.payment_method.vipps_polling_interval || 2) * 1000;
        const timeout = (this.payment_method.vipps_payment_timeout || 300) * 1000;
        const startTime = Date.now();

        this.pollingInterval = setInterval(async () => {
            try {
                // Check for timeout
                if (Date.now() - startTime > timeout) {
                    this.stopStatusPolling();
                    await this.send_payment_cancel();
                    this.notification.add(_t("Payment timeout - transaction cancelled"), {
                        type: "warning"
                    });
                    this.paymentStatus = 'timeout';
                    return;
                }

                // Poll status
                const result = await this.env.services.rpc({
                    model: 'payment.transaction',
                    method: 'poll_pos_payment_status',
                    args: [transactionId],
                });

                if (result.status === 'authorized' || result.status === 'done') {
                    this.stopStatusPolling();
                    this.paymentStatus = 'completed';
                    
                    // Mark payment as successful
                    const order = this.pos.get_order();
                    const paymentLine = order.selected_paymentline;
                    if (paymentLine) {
                        paymentLine.set_payment_status('done');
                        paymentLine.transaction_id = transactionId;
                    }
                    
                    this.notification.add(_t("Payment completed successfully"), {
                        type: "success"
                    });
                    
                } else if (result.status === 'cancelled' || result.status === 'failed') {
                    this.stopStatusPolling();
                    this.paymentStatus = 'failed';
                    
                    this.notification.add(_t("Payment was cancelled or failed"), {
                        type: "danger"
                    });
                }

            } catch (error) {
                console.error("Status polling error:", error);
            }
        }, pollInterval);
    }

    /**
     * Stop status polling
     */
    stopStatusPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    /**
     * Send payment cancel request
     * @returns {Promise<boolean>} Success status  
     */
    async send_payment_cancel() {
        try {
            const order = this.pos.get_order();
            const paymentLine = order.selected_paymentline;
            
            if (paymentLine && paymentLine.transaction_id) {
                await this.env.services.rpc({
                    model: 'payment.transaction',
                    method: 'cancel_pos_payment',
                    args: [paymentLine.transaction_id],
                });
            }
            
            this.stopStatusPolling();
            this.paymentStatus = 'cancelled';
            
            return true;
        } catch (error) {
            console.error("Payment cancellation failed:", error);
            return false;
        }
    }

    /**
     * Close payment interface
     */
    close() {
        this.stopStatusPolling();
        this.paymentStatus = 'idle';
        this.qrCodeData = null;
        this.shopNumber = null;
        this.customerPhone = '';
        super.close();
    }

    /**
     * Get current payment status for UI display
     * @returns {Object} Status information
     */
    getPaymentStatus() {
        return {
            status: this.paymentStatus,
            flow: this.selectedFlow,
            qrCode: this.qrCodeData,
            shopNumber: this.shopNumber,
            phone: this.customerPhone
        };
    }
}

// Register the payment interface
import { register } from "@web/core/registry";
register("payment_vipps", VippsPOSPaymentInterface);