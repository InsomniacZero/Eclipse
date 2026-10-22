# <img src="eclipse/static/logo.svg" width="38" height="38" alt="Eclipse Logo" style="vertical-align: middle; margin-right: 10px;" /> Eclipse

> **Free, unlimited, high-speed roleplay AI backend for JanitorAI & SillyTavern.**  
> **Google Gemini 4 Argon + Zhipu GLM-5 Thinking. $0/month. No paid API keys.**

---

Eclipse turns regular free Google Gemini and Zhipu GLM sessions into a private, high-speed OpenAI-compatible reverse proxy at `http://localhost:5000/v1`. 

Instead of paying $20 to $50 every month for OpenAI or OpenRouter credits, or dealing with laggy public proxies that crash every 10 minutes, Eclipse runs locally on your PC or phone and gives you **unlimited roleplay with flagship models**.

---

## 🌟 Why Eclipse is Built for JanitorAI Roleplayers

- 💸 **100% Free Forever**: No OpenAI bills, no credit cards, no subscriptions.
- 👑 **Gemini 4 Argon & 3.8 Flash**: Google's top reasoning models tuned for expressive, high-context, non-repetitive narrative roleplay.
- 🧠 **GLM-5 Turbo & 4.7 with Zero Setup**: GLM works **instantly without needing any login or account** in guest mode!
- 🛡️ **Built-in 429 Rate-Limit Auto-Healer**: When upstream servers get busy, Eclipse catches rate limits and automatically regenerates fresh sessions in the background. No more red error banners interrupting your story!
- ⚡ **1-Click Cookie Auto-Discovery**: No tedious DevTools inspect elements. Eclipse automatically detects and imports your Google login from Chrome, Brave, Edge, or Firefox with one click.
- 📱 **Cross-Platform**: Runs on **Windows**, **Android (Termux)**, **Mac**, and **Linux**.
- 🌐 **Free 1-Click Mobile Tunnel**: Play JanitorAI on your phone while running Eclipse on your PC with built-in HTTPS tunneling (zero mixed-content errors).

---

## ⚡ Super Easy 1-Minute Setup

Choose your device below and follow the 3 quick steps:

### 🪟 Windows Users (PC / Laptop)

1. **Install Python 3.10+**:
   - Download the official installer from **[python.org](https://www.python.org/downloads/)**.
   - ⚠️ **VERY IMPORTANT**: On the first installer screen, **CHECK THE BOX** at the bottom that says **"Add python.exe to PATH"** before clicking Install Now!
2. **Download Eclipse**:
   - Click the green **Code** button at the top of this GitHub page and click **Download ZIP**.
   - Extract the ZIP folder anywhere on your computer (like your Desktop or Documents).
3. **Start Eclipse**:
   - Open the extracted folder and double-click **`start.bat`**.
   - Eclipse will set everything up automatically. Your browser will pop open at `http://localhost:5000`. You are ready!

---

### 📱 Android Phone Users (Termux)

You don't need a computer! You can run Eclipse directly on your Android phone:

1. **Install Termux**:
   - Download and install Termux from **[F-Droid](https://f-droid.org/en/packages/com.termux/)** *(⚠️ Do NOT install from the Google Play Store; the Play Store version is abandoned and broken)*.
2. **Paste This Single Command**:
   - Open Termux, copy the command below, paste it into Termux, and press **Enter**:
   ```bash
   pkg update -y && pkg install -y python git && git clone https://github.com/Nephis-opus/Eclipse.git && cd Eclipse && ./start.sh
   ```
3. **Play**:
   - Termux will download and start Eclipse. Open Chrome on your phone and go to `http://localhost:5000`.

---

### 🍎 Mac (macOS) Users

1. Open **Terminal** (press `Cmd + Space`, type `Terminal`, and press Enter).
2. Copy and paste this command, then press Enter:
   ```bash
   git clone https://github.com/Nephis-opus/Eclipse.git && cd Eclipse && ./start.sh
   ```
3. *(Alternatively, you can just double-click `start.command` in the Eclipse folder!)*
4. Your browser will open to `http://localhost:5000`.

---

### 🐧 Linux Users

Open your terminal and run:
```bash
git clone https://github.com/Nephis-opus/Eclipse.git && cd Eclipse && ./start.sh
```

---

## 🎮 How to Connect Eclipse to JanitorAI (Click-by-Click)

Once Eclipse is running (your terminal shows `Eclipse is Online!`), connecting it to JanitorAI takes less than 30 seconds:

```
Step 1: Open JanitorAI (janitorai.com) and start a chat with any bot.
Step 2: Look at the top right corner of the chat and click "API Settings" (or "Using Janitor").
Step 3: Switch the API mode tab from JanitorLLM to "Proxy".
Step 4: Under Proxy Configurations, click "+ New".
Step 5: Fill in these exact values:
```

| Setting Field | What to Type / Select |
| :--- | :--- |
| **Config Name** | `Eclipse` *(or whatever name you like)* |
| **Model** | `gemini-4-argon` *(or any model from the cheat sheet below)* |
| **Proxy URL** | `http://localhost:5000/v1/chat/completions`<br/>*(If playing on your phone via tunnel, use your ngrok HTTPS URL!)* |
| **API Key** | `sk-eclipse-local` *(or literally any random letters, Eclipse does not lock you out)* |

```
Step 6: Click "Save Settings" / "Save Configuration".
Step 7: Refresh your JanitorAI browser tab once to lock in the connection.
```

🎉 **That's it! Send a message to your bot and enjoy fast, uncensored, high-context roleplay!**

---

## 🎭 Model Cheat Sheet (Which One Should You Choose?)

Here is your quick guide to picking the best model for your JanitorAI chats:

| Model ID | Vibe & Roleplay Style | Setup Needed | Best For |
| :--- | :--- | :--- | :--- |
| **`gemini-4-argon`** | 👑 **The King of Roleplay.** Incredible prose, understands complex emotional subtext, never forgets character traits, long creative replies. | 1-Click Google Auto-Fetch | Deep romance, long-term story arcs, detailed novel-like writing. |
| **`gemini-3.8-flash`** | ⚡ **Lightning Fast & Witty.** Snappy replies, quick banter, almost zero wait time. | 1-Click Google Auto-Fetch | Fast-paced chats, daily roleplay, action sequences. |
| **`glm-4.7-think`** | 🧠 **Smart Reasoning & Uncensored.** Uses chain-of-thought to analyze character cards thoroughly before answering. | **ZERO ACCOUNTS!** (Works instantly in guest mode) | Users who don't want to log into Google; detailed reasoning; 429 auto-healed. |
| **`glm-5-turbo-think`** | 🚀 **Next-Gen Speed + Thinking.** Fast, descriptive, and handles complex multi-character roleplay. | **ZERO ACCOUNTS!** (Works instantly in guest mode) | Instant plug-and-play with zero setup. |

> 💡 **Tip:** To test any model instantly, type its ID into JanitorAI's **Model** box!

---

## 🔑 How to Add Accounts (Gemini vs GLM)

### 1. Zhipu GLM Models (`glm-4.7-think`, `glm-5-turbo-think`)
- **YOU DO NOT NEED TO DO ANYTHING!**
- GLM has built-in anonymous guest session generation.
- It works immediately the second you launch Eclipse.
- If upstream servers get busy, Eclipse's **429 Auto-Healer** automatically regenerates your session so your chats never break.

### 2. Google Gemini Models (`gemini-4-argon`, `gemini-3.8-flash`)
- **1-Click Auto-Fetch (Easiest)**:
  1. Open the Eclipse web control center at `http://localhost:5000`.
  2. Click on the **Accounts / Cookies** tab.
  3. Click the green button that says **"⚡ Auto-Fetch Gemini Session"**.
  4. Eclipse will automatically detect your logged-in Google account from Chrome, Brave, Edge, or Firefox, decrypt the session, and save it.
- **Multi-Account Stacking**:
  - You can add multiple Google accounts! Eclipse will round-robin between them automatically so you never hit message limits.

---

## 📱 Playing JanitorAI on Your Phone (Free 1-Click Tunnel)

Do you want to run Eclipse on your computer (or phone Termux) and chat on JanitorAI from your iPhone, Android, or tablet without getting "Network Error"?

Because `janitorai.com` uses HTTPS, mobile browsers will block `http://localhost`. Eclipse fixes this with a **free 1-click HTTPS tunnel**:

1. In your terminal where Eclipse is running, type:
   ```bash
   ./start.sh tunnel start
   ```
   *(Or on Windows: run `start.bat tunnel start`, or click "Start Tunnel" on `http://localhost:5000`)*
2. Eclipse will print your private secure HTTPS URL:
   ```
   [✓] Public HTTPS Tunnel Online:
   ➜ https://abc-123.ngrok-free.app
   ```
3. In JanitorAI, change your **Proxy URL** to:
   ```
   https://abc-123.ngrok-free.app/v1/chat/completions
   ```
4. Now you can roleplay from **any mobile device anywhere in the world**!

---

## ⚙️ Recommended JanitorAI Chat Settings

For the best experience with Gemini and GLM models, set these in your JanitorAI Generation Settings:

- **Temperature**: `0.85` to `1.05` *(Gemini writes much more creatively with temperature near 1.0)*
- **Max New Tokens**: `1024` or `2048` *(Ensures the AI doesn't cut off mid-sentence)*
- **Context Size**: `8192` to `16384` *(Gemini and GLM have huge context windows and handle massive cards with ease)*

---

## ✨ Companion Userscript (`eclipse-regex.user.js`)

Eclipse includes an optional custom userscript located in `userscripts/eclipse-regex.user.js`.

**What it does for JanitorAI:**
- Formats AI thinking tags (`<thought>`, `<options>`, `<tucao>`) into clean, collapsible visual boxes so they don't clutter your story.
- Adds custom markdown formatting and styled character dialogue bubbles.

**How to use:**
1. Install the **[Tampermonkey](https://www.tampermonkey.net/)** extension in your browser.
2. In your browser, open `http://localhost:5000/userscripts/eclipse-regex.user.js`.
3. Tampermonkey will ask to install it. Click **Install**. Done!

---

## ❓ Troubleshooting & Frequently Asked Questions

### 1. JanitorAI says "Network Error" or "Failed to fetch"
- **Are you playing on your phone?** Mobile browsers block `http://` on HTTPS sites like JanitorAI. Use the free ngrok tunnel: run `./start.sh tunnel start` and paste the `https://...` link into JanitorAI's Proxy URL.
- **Is Eclipse running?** Make sure your terminal window with Eclipse is still open and running.
- **Did you include `/chat/completions`?** Ensure the URL is `http://localhost:5000/v1/chat/completions` (not just `http://localhost:5000`).

### 2. JanitorAI says "Model not found"
- Double check your spelling in the "Model" box. It must match the model ID exactly (e.g. `gemini-4-argon`, `gemini-3.8-flash`, `glm-4.7-think`, or `glm-5-turbo-think`).

### 3. Windows says "'python' is not recognized as an internal or external command"
- You forgot to check the PATH box when installing Python! Download the installer again from [python.org](https://www.python.org/downloads/), run it, choose **Modify**, and check the box **"Add python.exe to PATH"**.

### 4. "Address already in use" or Port 5000 is busy
- Simply run:
  ```bash
  ./start.sh restart
  ```
  *(Or on Windows: `start.bat restart`)*. Eclipse will cleanly terminate any hanging old processes and reclaim port 5000 immediately.

### 5. Termux on Android says "Repository under maintenance" or errors out
- Make sure you installed Termux from **F-Droid**, not the Google Play Store. The Google Play Store version has been dead for years.

---

## 🛠️ Handy Commands (Terminal Cheat Sheet)

You don't need to touch the terminal often, but if you want quick control, run these in your Eclipse folder:

```bash
# Check status and active accounts
./start.sh status

# Test chat right inside the terminal
./start.sh chat "Hello there!" -m gemini-4-argon

# 1-Click import browser cookies
./start.sh autofetch gemini

# Start / stop the free mobile HTTPS tunnel
./start.sh tunnel start
./start.sh tunnel stop

# Clean restart
./start.sh restart
```
*(On Windows, replace `./start.sh` with `start.bat`)*.

---

## 💖 Credits & License

Built with ☕ for the roleplaying community by **Nephis** / **InsomniacZero**.  
Licensed under MIT. Open-source, private, and always 100% free.
