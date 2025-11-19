# SahraBot - Marzneshin Telegram Bot

A Telegram bot for managing users on the Marzneshin panel, featuring a multi-admin system and easy deployment with Docker.

---

## 🚀 Key Features

- **User Management:** Create, edit, delete, reset usage, and manage services for users.
- **Multi-Admin:** Define multiple admins with their own panel credentials. The bot automatically respects the permissions each admin has within the Marzneshin panel.
- **Search:** Search for users via text, subscription link, and **inline mode** that supports filtering by the user's creator.
- **Node Monitoring:** Provides a `sudo-only` menu to list nodes and run a background task to send alerts via Telegram if a node becomes unhealthy.
- **Notifications:** Receive real-time alerts for `Expired` and `Limited` users, sent directly to the responsible admin.
---

## ⚡️ Quick Installation

The only prerequisite is a Linux server (e.g., Ubuntu) with `sudo` access and `git` & `curl` installed.

Run the following command in your server's terminal. The script is interactive and will guide you through the setup process automatically.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/BiMaghz/SahraBot/main/setup.sh)