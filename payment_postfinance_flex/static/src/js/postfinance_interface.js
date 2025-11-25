/** @odoo-module **/

import publicWidget from '@web/legacy/js/public/public_widget';
import { _t } from "@web/core/l10n/translation";
import { renderToMarkup } from "@web/core/utils/render";
import { PostfinanceIframeDialog } from "../js/iframe_dialog";

publicWidget.registry.PaymentForm.include({
    /**
     * Redirect the customer by submitting the redirect form included in the processing values.
     * This method extends the standard redirect flow to handle PostFinance-specific behavior.
     *
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    _processRedirectFlow: function(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'postfinance' || (providerCode === 'postfinance' && processingValues['api_url'])) {
            return this._super(...arguments);
        }

        const div = document.createElement('div');
        div.innerHTML = processingValues['redirect_form_html'];
        this.redirectForm = div.querySelector('form');
        this.redirectForm.setAttribute('id', 'o_payment_redirect_form');

        if (providerCode !== 'postfinance' || (providerCode === 'postfinance' && processingValues['postfinance_javascript_url'])) {
            this._showPostfinanceInterface();
        }

        this.redirectForm.setAttribute('target', '_top');

        document.body.appendChild(this.redirectForm);
    },

    /**
     * Display the PostFinance payment interface in a dialog
     * This creates an iframe through the PostFinance handler SDK
     */
    _showPostfinanceInterface: function() {
        var self = this;

        const formData = new FormData(this.redirectForm);
        const postfinance_javascript_url = formData.get("postfinance_javascript_url");
        let postfinance_payment_method = formData.get("postfinance_payment_method");

        try {
            if (postfinance_payment_method) {
                postfinance_payment_method = JSON.parse(postfinance_payment_method);
            }
        } catch (e) {
            console.log('PostFinance: Failed to parse payment method');
        }

        if (!postfinance_javascript_url || !postfinance_payment_method) {
            console.log('PostFinance: Missing required data');
            return;
        }

        var content = renderToMarkup("postfinance_interface.display_interface", {});
        self.dialog = this.call("dialog", "add", PostfinanceIframeDialog, {
            body: content,
            confirm: () => {
                self.footerConfirmButton = $('.btn-primary.btn-confirm');
                self.disableButton(self.footerConfirmButton, true); // Disable with loading spinner
                self.footerCloseButton = $('.btn.btn-secondary.btn-close-modal');
                self.disableButton(self.footerCloseButton); // Disable without spinner

                if (self.postfinanceHandler) {
                    self.postfinanceHandler.validate();
                }
            },
            cancel: () => {
                self.footerCloseButton = $('.btn-secondary.btn-close-modal');
                self.disableButton(self.footerCloseButton, true); // Disable with loading spinner
                self.footerConfirmButton = $('.btn-primary.btn-confirm');
                self.disableButton(self.footerConfirmButton); // Disable without spinner
                location.reload(true); // Force page reload from server
            },
        });

        $.getScript(postfinance_javascript_url)
            .done(function(script, textStatus) {
                if (typeof window.IframeCheckoutHandler !== 'function') {
                    $('ul.postfinance-payment-errors').text(_t("Payment interface failed to load"));
                    return;
                }

                try {
                    // Initialize iframe handler with payment method information
                    self.postfinanceHandler = new IframeCheckoutHandler(postfinance_payment_method);

                    $(document).ready(function() {
                        // Verify payment form container exists
                        if (!$('#postfinance-payment-form').length) {
                            console.log('PostFinance: Payment form element not found in DOM');
                        }

                        self.postfinanceHandler.create('postfinance-payment-form');
                    });

                    self.postfinanceHandler.setValidationCallback(function(validationResult) {
                        $('ul.postfinance-payment-errors').html(''); // Clear previous errors

                        if (validationResult.success) {
                            self.postfinanceHandler.submit();
                        } else {
                            self.enableButton();
                            $.each(validationResult.errors, function(index, errorMessage) {
                                $('ul.postfinance-payment-errors').append('<li>' + errorMessage + '</li>');
                            });
                        }
                    });

                    self.postfinanceHandler.setHeightChangeCallback(function(height) {
                    });

                    self.postfinanceHandler.setInitializeCallback(function() {
                        self.enableButton();
                    });
                } catch (e) {
                    $('ul.postfinance-payment-errors').text(_t("Failed to initialize payment form"));
                }
            })
            .fail(function(jqxhr, settings, exception) {
                $('ul.postfinance-payment-errors').text(_t("Failed to load payment interface"));
            });

        self._enableButton();
    },

    /**
     * Disable a button and optionally add a loading spinner
     *
     * @param {jQuery} $button - Button element to disable
     * @param {boolean} loader - Whether to show a loading spinner
     */
    disableButton: function($button, loader) {
        loader = loader || undefined;
        $button.attr('disabled', true);

        if (loader) {
            $button.children('.fa-lock').removeClass('fa-lock');
            $button.prepend('<span class="o_loader"><i class="fa fa-refresh fa-spin"></i>&nbsp;</span>');
        }
    },

    /**
     * Enable iframe buttons and remove loading spinners
     * Also unblocks UI using Odoo's UI service
     */
    enableButton: function() {
        var buttons = [$("#iframe_confirm"), $("#iframe_cancel")];

        buttons.forEach(function(button) {
            button.attr('disabled', false);
            button.children('.fa').addClass('fa-lock');
            button.find('span.o_loader').remove();
        });

        this.call('ui', 'unblock');
    },
});
