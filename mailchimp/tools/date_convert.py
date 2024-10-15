from datetime import datetime


def mailchimp_date_to_datetime(date_str):
    """
    Convert a MailChimp date string to a datetime object.
    @param date_str: MailChimp date string
    @return: datetime object
    """
    date_without_tz = date_str[:19]
    if date_without_tz:
        return datetime.strptime(date_without_tz, "%Y-%m-%dT%H:%M:%S")
    return False
