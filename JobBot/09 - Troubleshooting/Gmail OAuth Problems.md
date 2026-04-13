---
tags:
  - troubleshooting
  - reference
  - current
---

# Gmail OAuth Problems

Common Gmail authorization issues and how to fix them.

## Token expired / "invalid_grant" error

**Symptom:** Email sending fails with `invalid_grant` or `Token has been expired or revoked`.
**Fix:** Delete `%APPDATA%\JobBot\token.json` and restart JobBot. The next run with Gmail enabled will open a browser window for re-authorization.

> [!tip] When in doubt, delete token.json
> The token is automatically recreated on next run. Deleting it is safe and fixes most Gmail auth issues.

## "403 Access Blocked — This app is blocked"

**Symptom:** Browser shows an error during the OAuth flow saying the app is blocked.
**Cause:** The OAuth consent screen is in "External" mode and your email isn't added as a test user.
**Fix:**
1. Go to Google Cloud Console → APIs & Services → OAuth consent screen
2. Under "Test users", add your Gmail address
3. Try the authorization flow again

## Client secrets file not found

**Symptom:** Error mentioning `client_secrets_file` or `FileNotFoundError`.
**Fix:** Check that the path in **Client secrets path** in the Config Tab points to your actual `client_secret_*.json` file. Use an absolute path (e.g., `C:\Users\YourName\client_secret_12345.json`).

## Wrong Gmail scopes

**Symptom:** Authorization completes but sending fails with a permissions error.
**Cause:** The OAuth consent screen scope doesn't include `gmail.send`.
**Fix:** In Google Cloud Console, edit the consent screen scopes to include `https://www.googleapis.com/auth/gmail.send`, then delete `token.json` and re-authorize.

## Related Notes

- [[Gmail Delivery Setup]]
- [[Email Delivery via Gmail]]
- [[File Locations on Your Computer]]
