import os, secrets, hashlib, base64
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="London Bae Etsy Bridge")

KEY = os.getenv("ETSY_KEYSTRING")
SECRET = os.getenv("ETSY_SHARED_SECRET")
REDIRECT = os.getenv("ETSY_REDIRECT_URI")
SCOPES = os.getenv("ETSY_SCOPES", "listings_r listings_w shops_r shops_w")
SHOP = os.getenv("ETSY_SHOP_NAME", "LondonBaeDesigns")

states = {}
tokens = {}

def cfg():
    missing=[k for k,v in {"ETSY_KEYSTRING":KEY,"ETSY_SHARED_SECRET":SECRET,"ETSY_REDIRECT_URI":REDIRECT}.items() if not v]
    if missing: raise HTTPException(500, "Missing: " + ", ".join(missing))

def pkce():
    verifier=secrets.token_urlsafe(48)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier,challenge

@app.get("/health")
async def health():
    return {"ok":True,"shop":SHOP,"configured":bool(KEY and SECRET and REDIRECT)}

@app.get("/", response_class=HTMLResponse)
async def home():
    return f"<h1>London Bae Etsy Bridge</h1><p>Shop: <b>{SHOP}</b></p><p><a href='/oauth/start'>Authorize Etsy</a></p>"

@app.get("/oauth/start")
async def oauth_start():
    cfg()
    state=secrets.token_urlsafe(24)
    verifier,challenge=pkce()
    states[state]=verifier
    params={
        "response_type":"code",
        "redirect_uri":REDIRECT,
        "scope":SCOPES,
        "client_id":KEY,
        "state":state,
        "code_challenge":challenge,
        "code_challenge_method":"S256",
    }
    return RedirectResponse("https://www.etsy.com/oauth/connect?"+urlencode(params))

@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code:str,state:str):
    cfg()
    verifier=states.pop(state,None)
    if not verifier: raise HTTPException(400,"Invalid OAuth state")
    data={
        "grant_type":"authorization_code",
        "client_id":KEY,
        "redirect_uri":REDIRECT,
        "code":code,
        "code_verifier":verifier,
    }
    headers={"Content-Type":"application/x-www-form-urlencoded","x-api-key":f"{KEY}:{SECRET}"}
    async with httpx.AsyncClient(timeout=30) as c:
        r=await c.post("https://api.etsy.com/v3/public/oauth/token",data=data,headers=headers)
    if r.status_code>=400: raise HTTPException(r.status_code,r.text)
    j=r.json()
    tokens["access_token"]=j.get("access_token")
    tokens["refresh_token"]=j.get("refresh_token")
    return "<h2>Etsy authorization succeeded</h2><p>You can close this window.</p>"

def auth_headers():
    cfg()
    token=tokens.get("access_token")
    if not token: raise HTTPException(401,"Authorize at /oauth/start first")
    return {"Authorization":f"Bearer {token}","x-api-key":f"{KEY}:{SECRET}"}

@app.get("/etsy/me")
async def etsy_me():
    async with httpx.AsyncClient(timeout=30) as c:
        r=await c.get("https://api.etsy.com/v3/application/users/me",headers=auth_headers())
    if r.status_code>=400: raise HTTPException(r.status_code,r.text)
    return r.json()
