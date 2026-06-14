# Deploying PokeHart Collectors (free, family-accessible)

Goal: a permanent URL **`https://pokehartcollectors.streamlit.app`**, password-protected,
showing the gallery + the data we've gathered.

> The cloud is a **showcase** (browse sets, products, images, latest prices). Live price
> refresh runs on your home PC (`python run.py prices`) — datacenters get blocked by eBay.
> To update the online data later: re-run prices at home, then push the change (Step 5).

---

## 1. Make a GitHub account (free, ~2 min)
- Go to **github.com** → Sign up. Verify your email.

## 2. Put the code on GitHub with GitHub Desktop (easiest, no command line)
- Download **GitHub Desktop** from **desktop.github.com**, install, and sign in with your new account.
- File → **Add local repository** → choose the folder **`D:\Project Pokemon`**.
  (It's already a git repo with an initial commit — GitHub Desktop will recognise it.)
- Click **Publish repository**.
  - Name: `pokehart-collectors`
  - ✅ **Keep this code private** (tick it — keeps the data private)
  - Publish.

## 3. Make a Streamlit Cloud account
- Go to **share.streamlit.io** → **Sign in with GitHub** → authorise it.

## 4. Deploy the app
- Click **Create app** → **Deploy a public app from GitHub** (it can read your private repo).
- Fill in:
  - **Repository:** `your-username/pokehart-collectors`
  - **Branch:** `main`
  - **Main file path:** `tracker/dashboard/app.py`
  - **App URL:** change the subdomain to **`pokehartcollectors`** → so it becomes
    `pokehartcollectors.streamlit.app` (if taken, try `pokehart-collectors`).
- Click **Advanced settings → Secrets** and paste:
  ```toml
  app_password = "the-password-you-want-to-give-family"
  ```
- Click **Deploy**. First build takes a few minutes.

## 5. Updating the online data later (optional)
On your home PC:
```powershell
cd "D:\Project Pokemon"
.\.venv\Scripts\Activate.ps1
python run.py prices      # refresh eBay prices
python run.py check       # refresh stock
```
Then in **GitHub Desktop**: you'll see `data/tracker.db` changed → **Commit** → **Push**.
Streamlit Cloud auto-redeploys with the fresh data in ~1 minute.

---

### Share with family
Send them the URL + the password. Done. 🎉
