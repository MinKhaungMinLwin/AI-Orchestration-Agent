# T-Station AI for Hankook

## 🚀 Deployment

### 1. Install Dependencies

Install **Just** (task runner):

```bash
curl -fsSL https://just.systems/install.sh | sudo bash -s -- --to /usr/local/bin
```

---

### 2. Environment Setup

Create or update the `.env` file:

```env
# Replace ADD_KEY with your key
```

---

### 3. Start Application

```bash
just start
```

---

### 4. API Access & Test

* **Base URL**

```
http://{YOUR_IP}:{NGINX_PORT}/api
```

* **Authentication**

```
Authorization: Bearer {API_SECRET_KEY}
```

* **Test API**

```bash
curl -X GET \
  "http://{YOUR_IP}:7777/api/test/success" \
  -H "accept: application/json" \
  -H "Authorization: Bearer {API_SECRET_KEY}"
```

---

## 2. 🛠️ Development
- Dependency
```bash
curl -fsSL https://just.systems/install.sh | bash -s -- --to /usr/local/bin
curl -LsSf https://astral.sh/uv/install.sh | sh
```

- Helper
```bash
just help
```

-  Developer mode: You must have python 3.12 to activate
```bash
source {your_py312_venv_path}/bin/activate
```

```bash
// Example
(py3.12) @user:~/dr-prompt: just setup
(py3.12) @user:~/dr-prompt: source .venv/bin/activate
```
