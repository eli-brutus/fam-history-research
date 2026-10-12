"""Fail closed until current official base64/job/result schema can be verified.

No endpoint fields are guessed, and no image or credential is transmitted.
"""


class TranskribusOCRProvider:
    name = "transkribus"
    model = "148545"
    api_version = "v2"

    def __init__(self):
        raise RuntimeError("Transkribus adapter is blocked: the guides are verified, but the linked official API reference at api-staging.transkribus.org/docs is denied by the cloud network policy. Verify the current /v2/processes Image base64 and result schemas before implementing or making paid calls. No alternative model is used.")
