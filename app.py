import os, secrets, hashlib, base64
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="London Bae Etsy Bridge")

KEY = os.getenv("ETSY_KEYSTRING")
SECRET = os.getenv("ETSY_SHARED_SECRET")
REDIRECT = os.getenv("ETSY_REDIRECT_URI")
SCOPES = os.getenv("ETSY_SCOPES", "listings_r listings_w shops_r shops_w")
SHOP = os.getenv("ETSY_SHOP_NAME", "LondonBaeDesigns")
SHOP_ID = os.getenv("ETSY_SHOP_ID", "68119541")

states = {}
tokens = {}

def cfg():
    missing = [k for k, v in {
        "ETSY_KEYSTRING": KEY,
        "ETSY_SHARED_SECRET": SECRET,
        "ETSY_REDIRECT_URI": REDIRECT
    }.items() if not v]
    if missing:
        raise HTTPException(500, "Missing: " + ", ".join(missing))

def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge

@app.get("/health")
async def health():
    return {
        "ok": True,
        "shop": SHOP,
        "shop_id": SHOP_ID,
        "configured": bool(KEY and SECRET and REDIRECT)
    }

@app.get("/", response_class=HTMLResponse)
async def home():
    return f"""
    <h1>London Bae Etsy Bridge</h1>
    <p>Shop: <b>{SHOP}</b> ({SHOP_ID})</p>
    <p><a href='/oauth/start'>Authorize Etsy</a></p>
    <p><a href='/etsy/me'>Test user connection</a></p>
    <p><a href='/etsy/shop'>Test shop connection</a></p>
    <p><a href='/etsy/taxonomy'>View seller taxonomy</a></p>
    """

@app.get("/oauth/start")
async def oauth_start():
    cfg()
    state = secrets.token_urlsafe(24)
    verifier, challenge = pkce()
    states[state] = verifier
    params = {
        "response_type": "code",
        "redirect_uri": REDIRECT,
        "scope": SCOPES,
        "client_id": KEY,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return RedirectResponse("https://www.etsy.com/oauth/connect?" + urlencode(params))

@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code: str, state: str):
    cfg()
    verifier = states.pop(state, None)
    if not verifier:
        raise HTTPException(400, "Invalid OAuth state")
    data = {
        "grant_type": "authorization_code",
        "client_id": KEY,
        "redirect_uri": REDIRECT,
        "code": code,
        "code_verifier": verifier,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "x-api-key": f"{KEY}:{SECRET}"
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://api.etsy.com/v3/public/oauth/token",
            data=data,
            headers=headers
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    j = r.json()
    tokens["access_token"] = j.get("access_token")
    tokens["refresh_token"] = j.get("refresh_token")
    return "<h2>Etsy authorization succeeded</h2><p>You can close this window.</p>"

def auth_headers():
    cfg()
    token = tokens.get("access_token")
    if not token:
        raise HTTPException(401, "Authorize at /oauth/start first")
    return {
        "Authorization": f"Bearer {token}",
        "x-api-key": f"{KEY}:{SECRET}"
    }

@app.get("/etsy/me")
async def etsy_me():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            "https://api.etsy.com/v3/application/users/me",
            headers=auth_headers()
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return r.json()

@app.get("/etsy/shop")
async def etsy_shop():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"https://api.etsy.com/v3/application/shops/{SHOP_ID}",
            headers=auth_headers()
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return r.json()

@app.get("/etsy/taxonomy")
async def etsy_taxonomy():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            "https://api.etsy.com/v3/application/seller-taxonomy/nodes",
            headers=auth_headers()
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return r.json()

@app.post("/etsy/draft-listing")
async def create_draft_listing(payload: dict = Body(...)):
    """
    Creates a DRAFT listing only. This endpoint never activates/publishes listings.
    """
    allowed = {
        "quantity", "title", "description", "price", "who_made", "when_made",
        "taxonomy_id", "type", "is_supply", "should_auto_renew", "tags", "materials"
    }
    data = {k: v for k, v in payload.items() if k in allowed}
    required = ["quantity", "title", "description", "price", "who_made", "when_made", "taxonomy_id"]
    missing = [k for k in required if k not in data]
    if missing:
        raise HTTPException(400, "Missing required fields: " + ", ".join(missing))
    data.setdefault("type", "download")

    form = []
    for k, v in data.items():
        if isinstance(v, list):
            for item in v:
                form.append((k, str(item)))
        else:
            form.append((k, str(v).lower() if isinstance(v, bool) else str(v)))

    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            f"https://api.etsy.com/v3/application/shops/{SHOP_ID}/listings",
            data=form,
            headers=auth_headers()
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return r.json()
