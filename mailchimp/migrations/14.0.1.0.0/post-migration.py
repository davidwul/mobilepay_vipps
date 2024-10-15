from openupgradelib import openupgrade


def migrate(cr, version):
    old_list_col = openupgrade.get_legacy_name("list_id")
    cr.execute(
        f"""
    UPDATE mailchimp_merge_field
    SET list_id = l.odoo_list_id
    FROM mailchimp_lists l
    WHERE {old_list_col} = l.id
    """
    )
