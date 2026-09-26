"""SFTP key validation (services/intake/sftp_keys.py). Public keys only (the private halves were discarded at creation);
expected fingerprints are exactly what `ssh-keygen -lf` printed for them."""
from __future__ import annotations

import pytest

from services.intake.sftp_keys import SftpKeyError, parse

ED = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMLCTi3EzForfWT5GQ1LXQV01+QOBoBBQ2x7zUx6JWnU core-banking@test"
RSA2048 = ("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC2fF9Jt5tpRrGeDTXJiyV81zd3R1DkDM54V+3GuZq1a3pa7DKjsUr4kooMaRRwybx7QZ5JiVlNwX9k"
           "5WTwPsUuSPpAhrcS140hlSzVpYtCG1Vcnf1jrrWRudpteuisfnPT7bDQGtUiSdIUv9tUWCWC0UypL6xM9MFTsWWFexIWlEd5z+8vuZjB0fDsgJpg5Oh7pm"
           "RFZ9MOGjwNy4Ta5iimDNe6iHarD5Vq1W8CN3xrVAkyacwktouaswAascgKFwpHufPdL8yW6DpMK8OUGk6nmWz1Vq+uGLp8xSjxZtLYkLJtw9H/Q0JxUI/I+K"
           "ZSICbnc1LH0M14+xf1ZgLZPgJj old@test")
RSA3072 = ("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDLOtvuWKpjmCH48Dh0hyTSPWR3/QMyQ5Y+c8cXclF1Y5E/nc1ysJ4SvaxskHaVgP5ktzAh+ja53qj/g"
           "hvZujaCQYKQ0z7Ahx78Mu9DPprhynlK0giZmlZ6ymVxB6DlR9y74jMHJ42ynZVrvtD5rjneu0NHDbwgdEOK939L6j7NlxzX1O+w6aQsxSH3a2H1JG1FfQ+n4"
           "xfeMHDAcFcYnXEU0bAcBK89uXl1LVRzeA3VKTsfS3F9iMW/vyzntlqxNElNrT3xKK/2LleBU6nNNESXArON/MTAYI8n7QWCEKfPx72bKo0weQeZg9a1Fr/Azsx"
           "XcC8RNwr3JpXb1ZH0E6R9XT0KjwqGFAusOrk3ZyEopXUYIUZ0kLs3LHXdTOp4t6xWLbr94OutRUC7NfBef5DHx12J9/LrL2RBfwIvSU6oWcEdxocrpa2Kfv"
           "vZ/LmQ5QSFqqwdei1dJBRB9474ynEYjQ93Y59w0q7MSnj6K3loacGWMOsK5RVoC3/OOHMllTM= rsa3k@test")


def test_fingerprints_match_ssh_keygen():
    assert parse(ED)["fingerprint"] == "SHA256:k8X8j55gMeYOp1yLjdkxwALAla+pSfqsYMDb0ayZoW8"
    k = parse(RSA3072)
    assert k["fingerprint"] == "SHA256:ZSg+xnYw+bcDYqXM1MLahAcVSFaYW9btKk1wqXiirgw" and k["bits"] == 3072
    assert parse(ED)["public_key"] == ED.rsplit(" ", 1)[0]          # comment not stored in the key itself


def test_weak_or_malformed_keys_are_refused():
    with pytest.raises(SftpKeyError, match="2048 bits"):
        parse(RSA2048)
    with pytest.raises(SftpKeyError, match="not accepted"):
        parse("ssh-dss AAAAB3NzaC1kc3M= x")
    with pytest.raises(SftpKeyError, match="does not match its type"):
        parse("ssh-rsa " + ED.split()[1])
    with pytest.raises(SftpKeyError, match="whole public key line"):
        parse("AAAAC3NzaC1lZDI1NTE5")
    with pytest.raises(SftpKeyError, match="not valid"):
        parse("ssh-ed25519 not*base64")
