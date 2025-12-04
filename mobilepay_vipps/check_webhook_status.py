import logging
_logger = logging.getLogger(__name__)
try:
    providers = env['payment.provider'].search([('code', '=', 'vipps')])
    if providers:
        provider = providers[0]
        result = provider.action_check_webhook_status()
        print(result)
    else:
        print("Vipps payment provider not found.")
except Exception as e:
    print(e)