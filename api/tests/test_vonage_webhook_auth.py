import time

import jwt
import pytest

from api.services.telephony.providers.vonage.provider import VonageProvider


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['valid', 'missing', 'wrong-key', 'wrong-account', 'stale', 'api-secret'])
async def test_vonage_requires_signed_account_bound_recent_callback(case):
    provider = VonageProvider({'api_key':'account', 'api_secret':'api-secret-not-signing-secret',
                               'signature_secret':'webhook-signing-secret-test-long-key',
                               'application_id':'application'})
    claims = {'iss':'Vonage','iat':int(time.time()),'api_key':'account','application_id':'application'}
    secret = provider.signature_secret
    if case == 'wrong-key': secret = 'invalid-signing-secret-test-long-key'
    if case == 'wrong-account': claims['api_key'] = 'other'
    if case == 'stale': claims['iat'] -= 900
    if case == 'api-secret': secret = provider.api_secret
    token = jwt.encode(claims, secret, algorithm='HS256')
    headers = {} if case == 'missing' else {'Authorization':f'Bearer {token}'}
    assert await provider.verify_inbound_signature('https://example.test/ncco',{},headers) is (case == 'valid')
