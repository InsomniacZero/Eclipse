# ☁️ Oracle Cloud Free Tier — 24/7 100% Free Eclipse Cloud Server Guide

> **Want Eclipse running 24/7 in the cloud so you can roleplay on JanitorAI from your phone anytime without keeping your computer on?**  
> This guide walks you through setting up an official **Always Free** cloud server on Oracle Cloud. It requires zero tech skills and costs **$0.00 forever**.

---

## 📌 Before You Start: 3 Quick Facts

1. **Is this actually 100% Free?**  
   **YES.** Oracle Cloud provides an official **"Always Free"** tier. It does not expire, and you will never be charged.
2. **Why does it ask for a credit/debit card?**  
   Just like Netflix or Spotify free trials, Oracle requires a card purely to verify that you are a real person and not an automated bot creating spam accounts.
3. **Will my card be charged?**  
   Oracle puts a temporary verification hold of **around $1 to $2** to verify the card is active. **This is NOT a charge** — the money is automatically released back to your bank account within a few business days.

---

## 📝 STEP 1: Sign Up for Oracle Cloud

1. Open this link in your web browser:  
   👉 **[https://www.oracle.com/cloud/free/](https://www.oracle.com/cloud/free/)**
2. Click the big button that says **"Start for free"**.
3. Fill in your details:
   - **Country/Territory**: Select your actual country.
   - **First Name & Last Name**: Your real name (matching your card).
   - **Email**: Your real email address.
4. Pass the robot captcha check and click **"Verify my email"**.
5. Open your email inbox, find the verification email from Oracle, and click the confirmation link.

---

## 🔑 STEP 2: Account Setup & Home Region

After clicking your email verification link, complete the account setup form:

1. **Password**: Create a secure password (at least 8 characters, with uppercase, lowercase, numbers, and a symbol like `!` or `@`).
2. **Cloud Account Name** (Tenancy Name):  
   - Type any simple lowercase name with no spaces (e.g. `eclipseserver24` or `rpcloud99`). Remember this name!
3. **Home Region** *(⚠️ CRITICAL: Choose a location closest to you)*:  
   - Select the city/region closest to where you live (e.g. US East Ashburn, US West Phoenix, Germany Frankfurt, London, Tokyo, etc.).
4. **Address & Phone**:
   - Enter your real billing address matching your card.
   - Enter your phone number and enter the SMS verification code.

---

## 💳 STEP 3: Payment Verification ($0 Hold)

1. Click **"Add Payment Verification Method"** ➔ Select **Credit Card**.
2. Enter your card details (Visa, Mastercard, or American Express).  
   *(Note: Most prepaid or temporary virtual cards are declined by Oracle, so use a real debit or credit card).*
3. Submit the form and complete your bank's authorization prompt if one appears.
4. Check the agreement box and click **"Complete Sign-Up"**.

> ⏳ *Wait 1–2 minutes while Oracle provisions your account. Once ready, you'll be redirected to the Oracle Cloud Dashboard.*

---

## 🖥️ STEP 4: Create the Free Server (Click-by-Click)

1. Go to the dashboard: **[https://cloud.oracle.com/](https://cloud.oracle.com/)** and log in.
2. In the top-left corner, click the **Hamburger Menu** (`☰`).
3. Click **Compute** ➔ then click **Instances**.
4. Click the blue button that says **"Create instance"**.

Now configure these exact settings:

### A. Name
- Type `eclipse-server` (or leave the default name).

### B. Image and Shape
1. Next to **Image**, click **Edit** ➔ **Change image**:
   - Select **Canonical Ubuntu**.
   - Under version, choose **Ubuntu 24.04** or **Ubuntu 22.04 Minimal**.
   - Click **Select image**.
2. Next to **Shape**, click **Edit** ➔ **Change shape**:
   - Select **Ampere** (ARM-based `VM.Standard.A1.Flex`).
   - If available, set OCPU to `2` and RAM to `12` GB (or up to `4` OCPUs and `24` GB RAM — all 100% Always Free!).
   - *If Ampere says "Out of host capacity", choose **AMD** ➔ `VM.Standard.E2.1.Micro` (Always Free).*
   - **Confirm it displays the green badge: "Always Free Eligible"**.
   - Click **Select shape**.

### C. Networking
- Leave everything as default (**"Create new virtual cloud network"** and **"Assign a public IPv4 address"** checked).

### D. 🔑 SSH Keys *(THE MOST IMPORTANT STEP!)*
- Under **Add SSH keys**, leave **"Generate SSH key pair"** selected.
- Click the button that says:
  👉 **"Save private key"** (This downloads a file like `ssh-key-xxxx.key`).
- Also click **"Save public key"**.
- ⚠️ **DO NOT LOSE THIS FILE! Save it on your computer.**

### E. Create!
- Scroll to the bottom and click the blue **"Create"** button.

---

## 🎯 STEP 5: Grab Your Public IP Address

1. You will be redirected to the instance details page.
2. The status badge will show **PROVISIONING** (orange).
3. Wait about 1 to 2 minutes until it turns **RUNNING** (green).
4. Look on the screen for **"Public IP Address"**:
   - It will look like `152.67.xxx.xxx`.
   - Click the copy button next to it.

---

## 🚀 STEP 6: Run Eclipse on Your Free Server

You can set this up yourself in 2 minutes!

### Method 1: Do It Yourself (Fast & Easy)

1. **Connect to Your Server**:
   - **On Windows**: Open PowerShell or Command Prompt.
   - **On Mac / Linux**: Open Terminal.
   - Type this command (replace `C:\path\to\your-key.key` and `YOUR_SERVER_IP` with your actual file path and IP):
     ```bash
     ssh -i "path/to/ssh-key-xxxx.key" ubuntu@YOUR_SERVER_IP
     ```
     *(If it asks "Are you sure you want to continue connecting?", type `yes` and press Enter)*.

2. **Run the 1-Line Eclipse Cloud Installer**:
   - Once connected, copy this single command, paste it into the terminal, and press Enter:
     ```bash
     sudo apt update -y && sudo apt install -y git python3 python3-venv && git clone https://github.com/InsomniacZero/Eclipse.git && cd Eclipse && ./start.sh
     ```
   - Eclipse will set up Python, install dependencies, and start the gateway!

3. **Expose It Over Free Secure HTTPS (No Port Forwarding Needed!)**:
   - In that same terminal, run:
     ```bash
     ./start.sh tunnel start
     ```
   - Eclipse will print out your private HTTPS URL:
     ```
     ➜ https://your-server.ngrok-free.app
     ```
   - Copy that URL!

4. **Connect JanitorAI**:
   - In JanitorAI's Proxy settings, set:
     - **Proxy URL**: `https://your-server.ngrok-free.app/v1/chat/completions`
     - **Model**: `gemini-4-argon` or `glm-4.7-think`
     - **API Key**: `sk-eclipse-local`
   - Enjoy 24/7 roleplay from your phone or PC without ever turning on your local computer again!

---

### Method 2: Let a Tech-Savvy Friend Set It Up For You

If you prefer not to touch the terminal, simply send your friend:
1. **The Public IP Address** (e.g. `152.67.45.120`).
2. **The Private Key file** you downloaded (`ssh-key-xxxx.key`).

They can log in, run the 1-line script, and give you your JanitorAI connection link in 60 seconds!

---

## 🔒 Keeping It Running in the Background 24/7 (Screen / Tmux)

If you disconnect from SSH, you want Eclipse to stay running forever. Use `screen`:

```bash
# Start a background session
screen -S eclipse

# Navigate to Eclipse and run
cd ~/Eclipse && ./start.sh

# Press Ctrl+A, then press D to detach from the screen safely!
```

To re-attach to Eclipse anytime:
```bash
screen -r eclipse
```

🎉 **Congratulations! You now have a private, 24/7 high-speed AI roleplay cloud server that costs $0.00!**
