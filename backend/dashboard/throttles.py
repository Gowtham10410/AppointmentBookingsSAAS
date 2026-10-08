from rest_framework.throttling import AnonRateThrottle


class OrgCodeLookupThrottle(AnonRateThrottle):
    rate = "30/minute"
    scope = "org_code_lookup"
