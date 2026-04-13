---
tags:
  - configuration
  - guide
  - current
related_code: gmail_client.py
---

# Gmail Delivery Setup

Step-by-step guide to connecting JobBot to your Gmail account for sending applications.

> [!warning] Keep your credentials private
> The `client_secret_*.json` file contains sensitive OAuth credentials. Never share it or commit it to git. JobBot's `.gitignore` already excludes it.

## Step 1 — Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (name it anything, e.g., "JobBot")
3. In the project, go to **APIs & Services → Library**
4. Search for "Gmail API" and click **Enable**

## Step 2 — Create OAuth credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Download the generated JSON file — it will be named `client_secret_*.json`

## Step 3 — Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**
2. User type: **External**
3. Add your Gmail address as a test user
4. Scopes: add `https://www.googleapis.com/auth/gmail.send`

## Step 4 — Point JobBot at the credentials file

In the Config Tab:
- **Client secrets path**: enter the full path to your `client_secret_*.json` file
- **Gmail sender**: your Gmail address
- **Enable Gmail delivery**: check the box
- Click **Save**

## Step 5 — First authorization

On the first run with Gmail enabled, a browser window will open asking you to authorize access. Sign in with your Gmail account and grant the permission. JobBot stores the resulting token in `%APPDATA%\JobBot\token.json`.

Subsequent runs use the saved token automatically and do not require re-authorization unless the token expires.

## Related Notes

- [[Email Delivery via Gmail]]
- [[Gmail OAuth Problems]]
- [[Approving and Sending Applications]]
