import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useChildRef } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

export class PostfinanceIframeDialog extends Component {
    static template = "payment_postfinance_flex.PostfinanceIframeDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: {
            validate: (m) => {
                return (
                    typeof m === "string" ||
                    (typeof m === "object" && typeof m.toString === "function")
                );
            },
            optional: true,
        },
        body: { type: String, optional: true },
        confirm: { type: Function, optional: true },
        confirmLabel: { type: String, optional: true },
        confirmClass: { type: String, optional: true },
        confirmId: { type: String, optional: true },
        cancel: { type: Function, optional: true },
        cancelLabel: { type: String, optional: true },
        cancelId: { type: String, optional: true },
    };

    static defaultProps = {
        confirmLabel: _t("Confirm"),
        cancelLabel: _t("Close"),
        confirmClass: "btn-primary btn-confirm",
        confirmId: "iframe_confirm",
        cancelId: "iframe_cancel",
        title: _t("Powered By PostFinance Interface"),
    };

    setup() {
        this.env.dialogData.dismiss = () => this._dismiss();
        this.modalRef = useChildRef();
    }

    async _cancel() {
        return this.execButton(this.props.cancel);
    }

    async _confirm() {
        return this.execButton(this.props.confirm);
    }

    async _dismiss() {
        return this.execButton(this.props.dismiss || this.props.cancel);
    }

    async execButton(callback) {
        if (callback) {
            await callback();
        }
    }
}