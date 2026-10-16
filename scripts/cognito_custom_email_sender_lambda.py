"""
AWS Lambda: Cognito Custom Email Sender

Use this ONLY if you need the SAME verification code on email AND SMS without SES.
Cognito invokes this Lambda with an KMS-encrypted code; you decrypt it, send email
(your own SMTP/SendGrid/etc. — not SES required), and call RingCentral SMS.

Setup (AWS Console):
1. Create a KMS key; note the key ARN.
2. User Pool → Extensions → Custom email sender → select this Lambda + KMS key.
3. Disable Cognito default email OR Custom sender replaces it (Lambda must send email).
4. Lambda env vars: KMS_KEY_ARN, RINGCENTRAL_* , SMTP_* or SENDGRID_* , FROM_PHONE_NUMBER
5. Grant Lambda: kms:Decrypt, cognito-idp permissions, VPC if needed.

Docs: https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-custom-email-sender.html
"""

import base64
import json
import os

import boto3


def _decrypt_code(kms_key_id: str, encrypted_code_b64: str) -> str:
    client = boto3.client("kms")
    blob = base64.b64decode(encrypted_code_b64)
    plain = client.decrypt(CiphertextBlob=blob)["Plaintext"]
    return plain.decode("utf-8")


def _send_sms(phone_e164: str, code: str) -> None:
    # Use RingCentral SDK or HTTPS call to your Flask /internal/sms endpoint
    from ringcentral import SDK

    sdk = SDK(
        os.environ["RC_CLIENT_ID"],
        os.environ["RC_CLIENT_SECRET"],
        os.environ.get("RC_SERVER", "https://platform.ringcentral.com"),
    )
    platform = sdk.platform()
    platform.login(jwt=os.environ["RC_JWT"])
    platform.post(
        "/restapi/v1.0/account/~/extension/~/sms",
        {
            "from": {"phoneNumber": os.environ["RC_FROM_NUMBER"]},
            "to": [{"phoneNumber": phone_e164}],
            "text": f"Your Vibrr verification code is: {code}",
        },
    )


def _send_email(to_address: str, code: str) -> None:
    # Example: SendGrid — replace with your provider (SMTP, Mailgun, etc.)
    import requests

    requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {os.environ['SENDGRID_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "personalizations": [{"to": [{"email": to_address}]}],
            "from": {"email": os.environ["EMAIL_FROM"]},
            "subject": "Your Vibrr verification code",
            "content": [
                {
                    "type": "text/plain",
                    "value": f"Your verification code is: {code}",
                }
            ],
        },
        timeout=30,
    )


def lambda_handler(event, context):
    trigger = event.get("triggerSource", "")
    if trigger not in (
        "CustomEmailSender_SignUp",
        "CustomEmailSender_ResendCode",
        "CustomEmailSender_ForgotPassword",
    ):
        return event

    code = _decrypt_code(os.environ["KMS_KEY_ARN"], event["request"]["code"])
    email = event["request"]["userAttributes"].get("email")
    phone = event["request"]["userAttributes"].get("phone_number")

    if email:
        _send_email(email, code)
    if phone:
        _send_sms(phone, code)

    return event
