/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * Vipps POS Payment Screen Component
 * Handles the complete payment flow interface for POS
 */
export class VippsPOSPaymentScreen extends Component {
    static template = "VippsPOSPaymentScreen";

    setup() {
        this.notification = useService("notification");
        this.rpc = useService("rpc");
        
        this.state = useState({
            currentStep: 'flow_selection', // flow_selection, payment_processing, payment_complete
            selectedFlow: null,
            customerPhone: '',
            phoneValidationMessage: '',
            paymentData: null,
            paymentStatus: 'idle',
            qrCodeData: null,
            shopNumber: null,
            shopQrCode: null,
            pollingInterval: null,
            timeoutTimer: null,
            elapsedTime: 0,
            maxTimeout: 300, // 5 minutes default
            errorMessage: null,
            isProcessing: false,
            // Real-time monitoring state
            statusHistory: [],
            lastStatusCheck: null,
            connectionStatus: 'connected',
            retryCount: 0,
            maxRetries: 3,
            progressPercentage: 0,
            estimatedTimeRemaining: null,
            paymentAttempts: 0,
            // Receipt integration
            receiptData: null,
            showReceiptPreview: false
        });

        onMounted(() => {
            this.loadPaymentMethodConfig();
            this.initializeStatusMonitoring();
        });

        onWillUnmount(() => {
            this.cleanup();
        });
    }

    /**
     * Load payment method configuration
     */
    async loadPaymentMethodConfig() {
        try {
            const config = await this.rpc("/pos/vipps/get_payment_config", {});
            this.state.maxTimeout = config.timeout || 300;
            this.paymentMethod = config.payment_method;
        } catch (error) {
            console.error("Failed to load payment config:", error);
        }
    }

    /**
     * Get available payment flows
     */
    getAvailableFlows() {
        if (!this.paymentMethod) return [];

        const flows = [];
        
        if (this.paymentMethod.vipps_enable_qr_flow) {
            flows.push({
                code: 'customer_qr',
                name: _t('Customer QR Code'),
                description: _t('Customer scans QR code with their mobile app'),
                icon: 'fa-qrcode',
                color: '#ff5722'
            });
        }
        
        if (this.paymentMethod.vipps_enable_phone_flow) {
            flows.push({
                code: 'customer_phone',
                name: _t('Phone Number'),
                description: _t('Send push message to customer\'s phone'),
                icon: 'fa-mobile',
                color: '#2196f3'
            });
        }
        
        if (this.paymentMethod.vipps_enable_manual_flows) {
            flows.push({
                code: 'manual_shop_number',
                name: _t('Shop Number'),
                description: _t('Customer enters shop number in their app'),
                icon: 'fa-keyboard-o',
                color: '#4caf50'
            }, {
                code: 'manual_shop_qr',
                name: _t('Shop QR Code'),
                description: _t('Customer scans shop-specific QR code'),
                icon: 'fa-qrcode',
                color: '#9c27b0'
            });
        }
        
        return flows;
    }

    /**
     * Select payment flow
     */
    selectPaymentFlow(flowCode) {
        this.state.selectedFlow = flowCode;
        this.state.customerPhone = '';
        this.state.phoneValidationMessage = '';
        this.state.errorMessage = null;
    }

    /**
     * Validate phone number
     */
    validatePhoneNumber(phone) {
        if (!phone) return false;
        
        // Nordic phone number validation (Norway, Denmark)
        const phoneRegex = /^(\+47|\+45|0047|0045)?\s?[0-9]{8}$/;
        const cleanPhone = phone.replace(/\s/g, '');
        
        if (!phoneRegex.test(cleanPhone)) {
            this.state.phoneValidationMessage = _t('Please enter a valid Nordic phone number (8 digits)');
            return false;
        }
        
        this.state.phoneValidationMessage = '';
        return true;
    }

    /**
     * Handle phone input change
     */
    onPhoneInputChange(event) {
        this.state.customerPhone = event.target.value;
        this.validatePhoneNumber(this.state.customerPhone);
    }

    /**
     * Check if payment can be started
     */
    canStartPayment() {
        if (!this.state.selectedFlow) return false;
        
        if (this.state.selectedFlow === 'customer_phone') {
            return this.validatePhoneNumber(this.state.customerPhone);
        }
        
        return true;
    }

    /**
     * Start payment process
     */
    async startPayment() {
        if (!this.canStartPayment()) return;

        this.state.isProcessing = true;
        this.state.errorMessage = null;

        try {
            // Get current order and payment line
            const order = this.env.pos.get_order();
            const paymentLine = order.selected_paymentline;
            
            if (!paymentLine) {
                throw new Error(_t("No payment line selected"));
            }

            // Prepare payment data
            const paymentData = {
                amount: paymentLine.amount,
                currency: this.env.pos.currency.name,
                reference: order.name,
                flow: this.state.selectedFlow,
                customer_phone: this.state.customerPhone,
                pos_session_id: this.env.pos.pos_session.id,
            };

            // Create payment
            const result = await this.rpc("/pos/vipps/create_payment", {
                payment_data: paymentData
            });

            if (result.success) {
                this.state.paymentData = result;
                this.state.qrCodeData = result.qr_code;
                this.state.shopNumber = result.shop_number;
                this.state.shopQrCode = result.shop_qr_code;
                this.state.currentStep = 'payment_processing';
                this.state.paymentStatus = 'waiting';
                
                // Start monitoring
                this.startPaymentMonitoring(result.transaction_id);
                
            } else {
                throw new Error(result.error || _t("Payment creation failed"));
            }

        } catch (error) {
            console.error("Payment start failed:", error);
            this.state.errorMessage = error.message || _t("Failed to start payment");
            this.notification.add(this.state.errorMessage, { type: "danger" });
        } finally {
            this.state.isProcessing = false;
        }
    }

    /**
     * Start payment monitoring
     */
    startPaymentMonitoring(transactionId) {
        this.state.elapsedTime = 0;
        
        // Start timeout timer
        this.state.timeoutTimer = setInterval(() => {
            this.state.elapsedTime += 1;
            
            if (this.state.elapsedTime >= this.state.maxTimeout) {
                this.handlePaymentTimeout();
            }
        }, 1000);

        // Start status polling
        const pollInterval = (this.paymentMethod?.vipps_polling_interval || 2) * 1000;
        this.state.pollingInterval = setInterval(async () => {
            await this.pollPaymentStatus(transactionId);
        }, pollInterval);
    }

    /**
     * Poll payment status
     */
    async pollPaymentStatus(transactionId) {
        try {
            const result = await this.rpc("/pos/vipps/poll_status", {
                transaction_id: transactionId
            });

            if (result.status === 'authorized' || result.status === 'done') {
                this.handlePaymentSuccess(result);
            } else if (result.status === 'cancelled' || result.status === 'failed') {
                this.handlePaymentFailure(result);
            }

        } catch (error) {
            console.error("Status polling error:", error);
        }
    }

    /**
     * Handle payment success
     */
    handlePaymentSuccess(result) {
        this.cleanup();
        this.state.paymentStatus = 'completed';
        this.state.currentStep = 'payment_complete';
        
        // Update payment line
        const order = this.env.pos.get_order();
        const paymentLine = order.selected_paymentline;
        if (paymentLine) {
            paymentLine.set_payment_status('done');
            paymentLine.transaction_id = result.transaction_id;
        }
        
        this.notification.add(_t("Payment completed successfully!"), { type: "success" });
    }

    /**
     * Handle payment failure
     */
    handlePaymentFailure(result) {
        this.cleanup();
        this.state.paymentStatus = 'failed';
        this.state.errorMessage = result.error || _t("Payment was cancelled or failed");
        this.notification.add(this.state.errorMessage, { type: "danger" });
    }

    /**
     * Handle payment timeout
     */
    async handlePaymentTimeout() {
        this.cleanup();
        this.state.paymentStatus = 'timeout';
        this.state.errorMessage = _t("Payment timed out");
        
        // Cancel the payment
        if (this.state.paymentData?.transaction_id) {
            try {
                await this.rpc("/pos/vipps/cancel_payment", {
                    transaction_id: this.state.paymentData.transaction_id
                });
            } catch (error) {
                console.error("Failed to cancel timed out payment:", error);
            }
        }
        
        this.notification.add(this.state.errorMessage, { type: "warning" });
    }

    /**
     * Cancel payment manually
     */
    async cancelPayment() {
        if (this.state.paymentData?.transaction_id) {
            try {
                await this.rpc("/pos/vipps/cancel_payment", {
                    transaction_id: this.state.paymentData.transaction_id
                });
                
                this.cleanup();
                this.state.paymentStatus = 'cancelled';
                this.notification.add(_t("Payment cancelled"), { type: "info" });
                
            } catch (error) {
                console.error("Failed to cancel payment:", error);
                this.notification.add(_t("Failed to cancel payment"), { type: "danger" });
            }
        }
    }

    /**
     * Cleanup timers and intervals
     */
    cleanup() {
        if (this.state.pollingInterval) {
            clearInterval(this.state.pollingInterval);
            this.state.pollingInterval = null;
        }
        
        if (this.state.timeoutTimer) {
            clearInterval(this.state.timeoutTimer);
            this.state.timeoutTimer = null;
        }
    }

    /**
     * Reset to flow selection
     */
    resetToFlowSelection() {
        this.cleanup();
        this.state.currentStep = 'flow_selection';
        this.state.selectedFlow = null;
        this.state.customerPhone = '';
        this.state.paymentStatus = 'idle';
        this.state.errorMessage = null;
        this.state.qrCodeData = null;
        this.state.shopNumber = null;
        this.state.shopQrCode = null;
    }

    /**
     * Close payment screen
     */
    closePaymentScreen() {
        this.cleanup();
        this.props.onClose?.();
    }

    /**
     * Format time display
     */
    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    /**
     * Get remaining time
     */
    getRemainingTime() {
        return Math.max(0, this.state.maxTimeout - this.state.elapsedTime);
    }

    /**
     * Format currency amount
     */
    formatCurrency(amount) {
        return this.env.pos.format_currency(amount);
    }

    /**
     * Verify manual payment completion
     */
    async verifyManualPayment() {
        if (!this.state.paymentData?.transaction_id) return;

        try {
            const result = await this.rpc("/pos/vipps/verify_manual_payment", {
                transaction_id: this.state.paymentData.transaction_id
            });

            if (result.success && result.verified) {
                this.handlePaymentSuccess(result);
            } else {
                // Show verification dialog or request cashier confirmation
                this.showManualVerificationDialog();
            }

        } catch (error) {
            console.error("Manual payment verification failed:", error);
            this.notification.add(_t("Failed to verify payment"), { type: "danger" });
        }
    }

    /**
     * Show manual verification dialog
     */
    showManualVerificationDialog() {
        // In a real implementation, this would show a dialog asking the cashier
        // to verify the payment on the customer's phone
        const confirmed = confirm(_t(
            "Please verify that the customer has completed the payment on their phone.\n\n" +
            "Check that:\n" +
            "- The payment amount matches: " + this.formatCurrency(this.state.paymentData.amount) + "\n" +
            "- The payment was successful\n" +
            "- The customer shows you the confirmation screen\n\n" +
            "Has the customer completed the payment?"
        ));

        if (confirmed) {
            this.confirmManualPayment();
        }
    }

    /**
     * Confirm manual payment after cashier verification
     */
    async confirmManualPayment() {
        try {
            // Mark the transaction as verified
            const order = this.env.pos.get_order();
            const paymentLine = order.selected_paymentline;
            if (paymentLine) {
                paymentLine.set_payment_status('done');
                paymentLine.transaction_id = this.state.paymentData.transaction_id;
            }

            this.state.paymentStatus = 'completed';
            this.state.currentStep = 'payment_complete';
            this.cleanup();

            this.notification.add(_t("Payment verified and completed!"), { type: "success" });

        } catch (error) {
            console.error("Failed to confirm manual payment:", error);
            this.notification.add(_t("Failed to confirm payment"), { type: "danger" });
        }
    }

    /**
     * Request payment proof from customer
     */
    requestPaymentProof() {
        this.notification.add(
            _t("Ask the customer to show you the payment confirmation on their phone"),
            { type: "info" }
        );
    }

    /**
     * Initialize status monitoring system
     */
    initializeStatusMonitoring() {
        // Set up connection monitoring
        this.state.connectionStatus = 'connected';
        this.state.lastStatusCheck = new Date();
        
        // Initialize progress tracking
        this.updateProgress(0);
    }

    /**
     * Enhanced payment monitoring with real-time updates
     */
    startPaymentMonitoring(transactionId) {
        this.state.elapsedTime = 0;
        this.state.retryCount = 0;
        this.state.paymentAttempts += 1;
        this.addStatusHistoryEntry('monitoring_started', 'Payment monitoring initiated');
        
        // Start timeout timer with progress updates
        this.state.timeoutTimer = setInterval(() => {
            this.state.elapsedTime += 1;
            
            // Update progress percentage
            const progressPercent = Math.min((this.state.elapsedTime / this.state.maxTimeout) * 100, 100);
            this.updateProgress(progressPercent);
            
            // Update estimated time remaining
            this.state.estimatedTimeRemaining = Math.max(0, this.state.maxTimeout - this.state.elapsedTime);
            
            if (this.state.elapsedTime >= this.state.maxTimeout) {
                this.handlePaymentTimeout();
            }
        }, 1000);

        // Start enhanced status polling
        const pollInterval = (this.paymentMethod?.vipps_polling_interval || 2) * 1000;
        this.state.pollingInterval = setInterval(async () => {
            await this.enhancedPollPaymentStatus(transactionId);
        }, pollInterval);
    }

    /**
     * Enhanced status polling with retry logic and connection monitoring
     */
    async enhancedPollPaymentStatus(transactionId) {
        try {
            this.state.connectionStatus = 'checking';
            this.state.lastStatusCheck = new Date();
            
            const result = await this.rpc("/pos/vipps/poll_status", {
                transaction_id: transactionId
            });

            // Reset retry count on successful connection
            this.state.retryCount = 0;
            this.state.connectionStatus = 'connected';
            
            // Add status to history
            this.addStatusHistoryEntry('status_check', `Status: ${result.status}`, result);

            if (result.status === 'authorized' || result.status === 'done') {
                this.handlePaymentSuccess(result);
            } else if (result.status === 'cancelled' || result.status === 'failed') {
                this.handlePaymentFailure(result);
            } else if (result.status === 'processing') {
                // Update progress for processing state
                this.updateProgress(Math.min(this.state.progressPercentage + 5, 80));
                this.addStatusHistoryEntry('processing', 'Payment is being processed');
            }

        } catch (error) {
            console.error("Enhanced status polling error:", error);
            this.handlePollingError(error, transactionId);
        }
    }

    /**
     * Handle polling errors with retry logic
     */
    async handlePollingError(error, transactionId) {
        this.state.retryCount += 1;
        this.state.connectionStatus = 'error';
        
        this.addStatusHistoryEntry('error', `Polling error (attempt ${this.state.retryCount}): ${error.message}`);
        
        if (this.state.retryCount >= this.state.maxRetries) {
            // Max retries reached, show connection error
            this.state.connectionStatus = 'disconnected';
            this.notification.add(
                _t("Connection lost. Payment may still be processing. Please check manually."),
                { type: "warning" }
            );
            
            // Continue polling but with longer intervals
            if (this.state.pollingInterval) {
                clearInterval(this.state.pollingInterval);
                this.state.pollingInterval = setInterval(async () => {
                    await this.enhancedPollPaymentStatus(transactionId);
                }, 10000); // 10 second intervals after max retries
            }
        } else {
            // Exponential backoff for retries
            const backoffDelay = Math.pow(2, this.state.retryCount) * 1000;
            setTimeout(() => {
                this.state.connectionStatus = 'reconnecting';
            }, backoffDelay);
        }
    }

    /**
     * Add entry to status history for monitoring
     */
    addStatusHistoryEntry(type, message, data = null) {
        const entry = {
            timestamp: new Date(),
            type: type,
            message: message,
            data: data
        };
        
        this.state.statusHistory.push(entry);
        
        // Keep only last 50 entries to prevent memory issues
        if (this.state.statusHistory.length > 50) {
            this.state.statusHistory.shift();
        }
        
        console.log(`[Vipps Status] ${entry.timestamp.toISOString()}: ${message}`);
    }

    /**
     * Update progress percentage and visual indicators
     */
    updateProgress(percentage) {
        this.state.progressPercentage = Math.min(Math.max(percentage, 0), 100);
        
        // Update progress-based status messages
        if (percentage < 20) {
            this.state.progressMessage = _t("Initializing payment...");
        } else if (percentage < 40) {
            this.state.progressMessage = _t("Waiting for customer action...");
        } else if (percentage < 60) {
            this.state.progressMessage = _t("Processing payment...");
        } else if (percentage < 80) {
            this.state.progressMessage = _t("Verifying payment...");
        } else if (percentage < 100) {
            this.state.progressMessage = _t("Finalizing...");
        } else {
            this.state.progressMessage = _t("Payment completed");
        }
    }

    /**
     * Enhanced payment success handling with receipt integration
     */
    handlePaymentSuccess(result) {
        this.cleanup();
        this.state.paymentStatus = 'completed';
        this.state.currentStep = 'payment_complete';
        this.updateProgress(100);
        
        this.addStatusHistoryEntry('success', 'Payment completed successfully', result);
        
        // Prepare receipt data
        this.prepareReceiptData(result);
        
        // Update payment line
        const order = this.env.pos.get_order();
        const paymentLine = order.selected_paymentline;
        if (paymentLine) {
            paymentLine.set_payment_status('done');
            paymentLine.transaction_id = result.transaction_id;
            
            // Add Vipps-specific receipt information
            paymentLine.vipps_receipt_data = {
                payment_method: this.state.selectedFlow,
                transaction_id: result.transaction_id,
                timestamp: new Date().toISOString(),
                status_history: this.state.statusHistory.slice(-5) // Last 5 status entries
            };
        }
        
        this.notification.add(_t("Payment completed successfully!"), { type: "success" });
        
        // Auto-close after showing receipt preview
        setTimeout(() => {
            if (this.state.showReceiptPreview) {
                this.state.showReceiptPreview = false;
            }
        }, 5000);
    }

    /**
     * Enhanced payment failure handling
     */
    handlePaymentFailure(result) {
        this.cleanup();
        this.state.paymentStatus = 'failed';
        this.state.errorMessage = result.error || _t("Payment was cancelled or failed");
        
        this.addStatusHistoryEntry('failure', `Payment failed: ${this.state.errorMessage}`, result);
        
        // Update progress to show failure
        this.updateProgress(0);
        
        this.notification.add(this.state.errorMessage, { type: "danger" });
    }

    /**
     * Enhanced timeout handling with automatic cancellation
     */
    async handlePaymentTimeout() {
        this.cleanup();
        this.state.paymentStatus = 'timeout';
        this.state.errorMessage = _t("Payment timed out");
        
        this.addStatusHistoryEntry('timeout', 'Payment timed out - initiating automatic cancellation');
        
        // Automatic payment cancellation
        if (this.state.paymentData?.transaction_id) {
            try {
                this.addStatusHistoryEntry('cancelling', 'Attempting automatic payment cancellation');
                
                await this.rpc("/pos/vipps/cancel_payment", {
                    transaction_id: this.state.paymentData.transaction_id
                });
                
                this.addStatusHistoryEntry('cancelled', 'Payment automatically cancelled due to timeout');
                
            } catch (error) {
                console.error("Failed to cancel timed out payment:", error);
                this.addStatusHistoryEntry('cancel_failed', `Failed to cancel payment: ${error.message}`);
                
                // Show manual intervention message
                this.notification.add(
                    _t("Payment timed out and automatic cancellation failed. Please check payment status manually."),
                    { type: "warning" }
                );
            }
        }
        
        this.notification.add(this.state.errorMessage, { type: "warning" });
    }

    /**
     * Prepare receipt data for integration
     */
    prepareReceiptData(paymentResult) {
        const order = this.env.pos.get_order();
        
        this.state.receiptData = {
            // Basic payment information
            amount: paymentResult.amount || this.state.paymentData?.amount,
            currency: this.env.pos.currency.name,
            payment_method: 'Vipps/MobilePay',
            flow_type: this.getFlowDisplayName(this.state.selectedFlow),
            
            // Transaction details
            transaction_id: paymentResult.transaction_id,
            reference: paymentResult.reference || order.name,
            timestamp: new Date().toISOString(),
            
            // Status information
            status: paymentResult.status,
            processing_time: this.state.elapsedTime,
            
            // Customer information (if available)
            customer_phone: this.state.customerPhone || null,
            
            // Technical details for troubleshooting
            payment_attempts: this.state.paymentAttempts,
            retry_count: this.state.retryCount,
            
            // Receipt display data
            receipt_lines: this.generateReceiptLines(paymentResult)
        };
        
        this.state.showReceiptPreview = true;
    }

    /**
     * Generate receipt lines for display
     */
    generateReceiptLines(paymentResult) {
        const lines = [];
        
        lines.push({
            type: 'header',
            text: 'VIPPS/MOBILEPAY PAYMENT'
        });
        
        lines.push({
            type: 'line',
            left: 'Amount:',
            right: this.formatCurrency(paymentResult.amount || this.state.paymentData?.amount)
        });
        
        lines.push({
            type: 'line',
            left: 'Method:',
            right: this.getFlowDisplayName(this.state.selectedFlow)
        });
        
        lines.push({
            type: 'line',
            left: 'Transaction ID:',
            right: paymentResult.transaction_id
        });
        
        lines.push({
            type: 'line',
            left: 'Time:',
            right: new Date().toLocaleString()
        });
        
        if (this.state.customerPhone) {
            lines.push({
                type: 'line',
                left: 'Phone:',
                right: this.state.customerPhone
            });
        }
        
        lines.push({
            type: 'separator'
        });
        
        lines.push({
            type: 'footer',
            text: 'Thank you for your payment!'
        });
        
        return lines;
    }

    /**
     * Get display name for payment flow
     */
    getFlowDisplayName(flowCode) {
        const flowNames = {
            'customer_qr': _t('Customer QR Code'),
            'customer_phone': _t('Phone Push Message'),
            'manual_shop_number': _t('Manual Shop Number'),
            'manual_shop_qr': _t('Manual Shop QR')
        };
        
        return flowNames[flowCode] || flowCode;
    }

    /**
     * Get connection status display information
     */
    getConnectionStatusInfo() {
        const statusInfo = {
            'connected': {
                icon: 'fa-wifi',
                color: '#4caf50',
                text: _t('Connected')
            },
            'checking': {
                icon: 'fa-spinner fa-spin',
                color: '#2196f3',
                text: _t('Checking...')
            },
            'reconnecting': {
                icon: 'fa-refresh fa-spin',
                color: '#ff9800',
                text: _t('Reconnecting...')
            },
            'error': {
                icon: 'fa-exclamation-triangle',
                color: '#f44336',
                text: _t('Connection Error')
            },
            'disconnected': {
                icon: 'fa-wifi',
                color: '#9e9e9e',
                text: _t('Disconnected')
            }
        };
        
        return statusInfo[this.state.connectionStatus] || statusInfo['disconnected'];
    }

    /**
     * Manual retry for failed connections
     */
    async retryConnection() {
        if (this.state.paymentData?.transaction_id) {
            this.state.retryCount = 0;
            this.state.connectionStatus = 'reconnecting';
            
            this.addStatusHistoryEntry('manual_retry', 'Manual connection retry initiated');
            
            try {
                await this.enhancedPollPaymentStatus(this.state.paymentData.transaction_id);
            } catch (error) {
                this.handlePollingError(error, this.state.paymentData.transaction_id);
            }
        }
    }

    /**
     * Show detailed status history
     */
    showStatusHistory() {
        const historyText = this.state.statusHistory
            .slice(-10) // Last 10 entries
            .map(entry => `${entry.timestamp.toLocaleTimeString()}: ${entry.message}`)
            .join('\n');
        
        alert(_t("Payment Status History:\n\n") + historyText);
    }
}