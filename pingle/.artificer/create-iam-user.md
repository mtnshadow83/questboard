# Create IAM User for EC2 Provisioning — Completed 2026-04-24

> IAM user `forge` created with EC2FullAccess. Keys stored in `forge3/keystore.db`.

You are on the IAM Dashboard. Follow these steps exactly.

## Step 1: Open IAM Users

On the left sidebar, under "Access Management", click **IAM users**.

## Step 2: Create User

Top right of the users table, click the **Create user** button.

## Step 3: Name the User

In the "User name" field, type: **forge**

Leave everything else default. Click **Next** at the bottom right.

## Step 4: Set Permissions

Select **Attach policies directly** (it's the third option).

In the search box that appears, type: **AmazonEC2FullAccess**

Check the box next to **AmazonEC2FullAccess** in the results.

Click **Next** at the bottom right.

## Step 5: Review and Create

Review the summary. You should see:
- User name: forge
- Permissions: AmazonEC2FullAccess

Click **Create user** at the bottom right.

## Step 6: Create Access Keys

You'll land on the users list. Click on **forge** to open the user.

Select the **Security credentials** tab (middle of the page, next to "Permissions").

Scroll down to "Access keys". Click **Create access key**.

Select **Command Line Interface (CLI)**.

Check the confirmation box at the bottom. Click **Next**.

Skip the description tag. Click **Create access key**.

## Step 7: Copy the Keys

You'll see two values:
- **Access key ID** (starts with AKIA...)
- **Secret access key** (click "Show" to reveal)

Copy both and paste them to me. This is the only time the secret key is shown.
