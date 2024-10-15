To configure this module, you need to:

- Go to Email Marketing \> Mailchimp \> Accounts
- Click on Create button to create a new account
- Enter the Account Name, API Key and Server Prefix and click on Save
  button

## Audiences / Lists

- Click on Fetch audiences button to fetch your mailing lists from
  Mailchimp
- From the Settings tab, you can control the synchronization of contacts
  between Odoo and Mailchimp. By default, modified contacts are exported
  every 4 hours.
- Go to Email Marketing \> Mailing Lists
- Edit the mailing lists you want to synchronize with Mailchimp
- Under the Mailchimp Settings tab, you can disable contacts export if
  you want.
- You can also synchronize the tags of the contacts if needed.

## Merge Fields

- Go to Email Marketing \> Mailing Lists \> Edit
- Click on Update Merge Fields button to fetch the merge fields from
  Mailchimp
- Edit the merge fields in order to fill the values from Odoo. You can
  write python expressions using the variable contact in order to fill
  the values dynamically from the mailing contact record.

## Webhook

- The module provides a webhook to receive contact updates and update
  your contact list in Odoo.
- On your MailChimp account, go to Audience \> Settings \> Webhooks and
  Create a New Webhook.
- Enter the URL of the webhook. The URL is
  https://\<your-odoo-server\>/mailchimp/webhook/.
- Select the updates you would like to receive in Odoo. Note that the
  Campaign sending update is not implemented.
- Make sure Via the API is not selected, unless you have other
  applications using the Mailchimp API.
