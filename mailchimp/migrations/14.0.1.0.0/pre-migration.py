from openupgradelib import openupgrade


def migrate(cr, version):
    openupgrade.rename_models(
        cr,
        [
            ("mailchimp.accounts", "mailchimp.account"),
            ("mailchimp.merge.fields", "mailchimp.merge.field"),
            ("mailchimp.templates", "mailchimp.template"),
        ],
    )
    openupgrade.rename_tables(
        cr,
        [
            ("mailchimp_accounts", "mailchimp_account"),
            ("mailchimp_merge_fields", "mailchimp_merge_field"),
            ("mailchimp_templates", "mailchimp_template"),
        ],
    )
    openupgrade.rename_columns(cr, {"mailchimp_merge_field": [("list_id", None)]})
